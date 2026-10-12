"""understando doctor: what is present, what is missing, and what went stale.

    understando doctor [--json]

Each finding has a severity: `mention` (the user must know; one sentence with its fix) or
`route` (a verb closes it; name the verb). An empty list is the good result. It checks:

- the toolchains: lake (Lean), java and tla2tools.jar (TLA+), the mutation venv (mutmut,
  cosmic-ray, pytest) and cc-check (Code Contracts);
- the required asd-ste100 skill, and the optional skills that understando routes to;
- the skill links and the CLI link;
- a link in the skill docs that points at no file;
- the evidence store: its schema, the code refs and control anchors at the head, and the drift
  of each formal record;
- the shape of the verify skill on the understando branch (create --check).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import coderef  # noqa: E402
import ste  # noqa: E402
import store  # noqa: E402
import toolprobe  # noqa: E402

ROUTED = ("create-verification-skill", "maintain-verification-skill", "lean-formal-feedback-loop", "code-contracts",
          "grilling", "tdd", "visual-explainer")
LINK_HOMES = (".agents/skills", ".claude/skills", ".codex/skills", ".cursor/skills")


def doc_links() -> list[str]:
    out = []
    for p in [store.ROOT / "SKILL.md", *sorted((store.ROOT / "commands").glob("*.md")), *sorted((store.ROOT / "references").rglob("*.md")),
              store.ROOT / "docs" / "DESIGN.md"]:
        if not p.is_file():
            continue
        for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", p.read_text(encoding="utf-8")):
            if re.match(r"^[a-z]+://", target) or target.startswith("mailto:"):
                continue
            if not (p.parent / target).exists():
                out.append(f"{p.relative_to(store.ROOT)} links {target}, which does not exist")
    return out


def findings(c: store.Ctx) -> list[dict]:
    out = []
    add = lambda sev, what, fix: out.append({"severity": sev, "what": what, "fix": fix})  # noqa: E731
    tools = toolprobe.tool_status()
    for name, fix in (("lake", "install elan (Lean)"), ("java", "install a JDK"), ("tla2tools", "put tla2tools.jar in ~/.understando/tools"),
                      ("mutmut", "run `understando setup --mutation`"), ("cosmic-ray", "run `understando setup --mutation`"),
                      ("cc-check", "run `understando setup` (npx @spolu/cc-check)")):
        if not tools.get(name):
            add("mention", f"{name} is missing", fix)
    if not ste.lint_path():
        add("mention", "the asd-ste100 skill is missing; it is required for the written claim text", "run `understando setup`")
    for name in ROUTED:
        if not toolprobe.find_skill(name):
            adapted = store.ROOT / "references" / "adapted" / f"{name}.md"
            add("mention", f"the optional skill {name} is not installed" + (f"; understando uses {adapted.relative_to(store.ROOT)}" if adapted.is_file() else ""),
                "install it to route to the original")
    home = Path.home()
    for h in LINK_HOMES:
        p = home / h / "understando"
        if p.is_symlink() and Path(os.path.realpath(p)) != store.ROOT.resolve():
            add("mention", f"{p} points at {os.path.realpath(p)}, not at this checkout", "run `bash scripts/setup.sh --links-only`")
    for line in doc_links():
        add("mention", line, "fix the link")
    data = c.data() if c.run else None
    if data is not None and c.repo:
        errors = store.validate(data)
        for e in errors[:10]:
            add("mention", f"the store is invalid: {e}", "fix the store, or run the verb that wrote it again")
        if not errors:
            for where, ref, at in coderef.walk_refs(data):
                try:
                    coderef.resolve_for(c.repo, data, ref, at)
                except coderef.AnchorError as exc:
                    add("route", f"{where} no longer resolves: {exc}", "write the ref again (understando snippet)")
            for k, where, e in coderef.walk_edits(data):
                if e.get("op") in coderef.ANCHOR_OPS and not k.get("sidecar"):
                    v = store.find(data, "checks", k["check"]) or {}
                    try:
                        coderef.resolve(c.repo, v.get("at") or data["head"], coderef.anchor_ref(e))
                    except coderef.AnchorError as exc:
                        add("route", f"{where}: the anchor no longer resolves: {exc}", "fix the control, then `understando probe`")
            import formal_record
            for v in data["checks"]:
                rec = v.get("formal_record") or {}
                d = rec.get("drift")
                if d and Path(d.get("root", "/nonexistent")).is_dir():
                    try:
                        if formal_record.drifted(rec, Path(d["root"])):
                            add("route", f"the proof of {v['id']} is older than its code or model", "understando formalize --recheck")
                    except formal_record.BrokenRecord as exc:  # a missing file is drift too
                        add("route", f"the proof of {v['id']} {exc}", "understando formalize --recheck")
            if data.get("skill"):
                import create
                for p in create.check_shape(c.repo, (data.get("ready") or {}).get("head") or "HEAD", data["skill"]):
                    add("route", f"the verify skill: {p}", "understando create --spec FILE --yes, or understando maintain")
    return out


def main(c: store.Ctx, argv: list[str]) -> int:
    rows = findings(c)
    if c.json:
        print(json.dumps({"findings": rows}, indent=2))
    elif not rows:
        print("doctor: every required piece is present, and nothing is stale.")
    else:
        for r in rows:
            print(f"{r['severity']}: {r['what']}. Fix: {r['fix']}.")
    return 0
