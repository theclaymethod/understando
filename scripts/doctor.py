"""understando doctor: drift and setup findings. Each finding has a severity that says what to do.

    understando doctor [--json] [--fix] [--pr-head SHA]

  auto     no decision needed: --fix applies it, and the report says what moved
  mention  the user must know; the finding offers a fix
  route    a verb closes it; the finding names the verb, and the user starts it

Checks: schema drift and stale stored verdicts; a trust map behind the PR head; a proof or a
model older than the code it covers (the drift gate); the Artifacture runtime path; the learn
sandbox (the learn app is paused); missing toolchains; routed skills (missing, or newer than the
adapted copy); a deleted @cc contract comment; stale imported evidence; the skill links.
An empty list is the good result.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ctx as context  # noqa: E402
import importers  # noqa: E402
import routes  # noqa: E402
import signals  # noqa: E402
import tm  # noqa: E402
import verdicts  # noqa: E402

SKILL_HOMES = [".agents/skills", ".claude/skills", ".claude/skills/pstack/skills", ".codex/skills", ".cursor/skills"]
LINK_HOMES = [".agents/skills", ".claude/skills", ".codex/skills", ".cursor/skills"]


def skill_found(name: str) -> str | None:
    home = Path(os.environ.get("HOME", str(Path.home())))
    for d in SKILL_HOMES:
        if (home / d / name / "SKILL.md").is_file():
            return str(home / d / name)
    return None


def cc_deleted(repo: Path, a: str, b: str) -> list[str]:
    """Each removed line that holds a @cc contract, as path: text."""
    out = subprocess.run(["git", "-C", str(repo), "diff", "-U0", "--no-renames", a, b], capture_output=True, text=True).stdout
    gone, path = [], None
    for line in out.splitlines():
        if line.startswith("--- "):
            path = line[6:] if line.startswith("--- a/") else None
        elif line.startswith("-") and not line.startswith("---") and "@cc" in line and path:
            gone.append(f"{path}: {line[1:].strip()[:80]}")
    return gone


def last_change(repo: Path, head: str, paths: list[str]) -> int:
    out = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%ct", head, "--", *paths], capture_output=True, text=True)
    return int(out.stdout.strip() or 0)


def findings(c: context.Ctx, explicit_head: str | None) -> tuple[list[dict], dict | None]:
    out: list[dict] = []

    def add(id_: str, severity: str, summary: str, fix: str, verb: str | None = None) -> None:
        out.append({"id": id_, "severity": severity, "summary": summary, "fix": fix, **({"verb": verb} if verb else {})})

    data = c.data()
    fixed = None
    if data:
        errors = tm.validate(data)
        if errors:
            add("schema-drift", "route", f"The trust map does not match the schema: {errors[0]}" + (f" (and {len(errors) - 1} more)" if len(errors) > 1 else ""),
                "Update the map to the current schema.", "map")
        else:
            before = json.dumps({k: data.get(k) for k in ("summary", "flags")}, sort_keys=True) + json.dumps([(x["id"], x.get("verdict"), x.get("tier")) for x in data["claims"]])
            fixed = json.loads(json.dumps(data))
            verdicts.apply(fixed)
            after = json.dumps({k: fixed.get(k) for k in ("summary", "flags")}, sort_keys=True) + json.dumps([(x["id"], x.get("verdict"), x.get("tier")) for x in fixed["claims"]])
            if before != after:
                add("stale-verdicts", "auto", "The stored verdicts, tiers or summary differ from the current rules.", "Write the verdicts again (verdicts.py).")
            else:
                fixed = None
        head = signals.pr_head(data, explicit_head)
        if head and head != data["head"]:
            add("stale-map", "route", f"The PR head moved: the map is at {data['head'][:10]}, the PR at {head[:10]}.", "Update the map and diff it.", "map")
        if c.repo:
            for v in data["verifiers"]:
                f = v.get("formal")
                if not f:
                    continue
                code = [r["path"] for cid in v["claims"] for cl in data["claims"] if cl["id"] == cid for r in cl.get("code", [])]
                if code and last_change(c.repo, data["head"], [f["artifact"]]) < last_change(c.repo, data["head"], code):
                    add("formal-drift", "route", f"{v['id']}: {f['artifact']} is older than the code it covers ({', '.join(sorted(set(code)))}).",
                        "Check the proof or model against the code again, then record the conformance run.", "formalize")
        if (c.run / "chapters").is_dir():
            first = sorted((c.run / "chapters").glob("01-*.mdx"))
            if first:
                line = first[0].read_text(encoding="utf-8").splitlines()[1]
                path = line.split("from '")[-1].split("/visual-explainer-mdx")[0] if "from '" in line else ""
                if path and not Path(path).is_dir():
                    add("runtime-path", "route", f"The chapters import a runtime that is not on this machine: {path}.",
                        "Build the explainer again with the current runtime.", "explain")
    ve = os.environ.get("UNDERSTANDO_VE_RUNTIME")
    if ve and not (Path(ve) / "visual-explainer-mdx" / "components.tsx").is_file():
        add("runtime-missing", "mention", f"UNDERSTANDO_VE_RUNTIME names {ve}, which holds no visual-explainer-mdx/components.tsx.",
            "Point UNDERSTANDO_VE_RUNTIME at an Artifacture checkout.")
    elif not ve and not skill_found("visual-explainer"):
        add("runtime-missing", "mention", "No Artifacture runtime: UNDERSTANDO_VE_RUNTIME is not set, and the visual-explainer skill is absent.",
            "Set UNDERSTANDO_VE_RUNTIME, or run setup.", "setup")
    learn_bin = tm.ROOT / "learn" / "target" / "release" / "understando-learn"
    if not learn_bin.is_file():
        add("learn-not-built", "mention", "The learn app is paused, and its binary is not built.", "Run learn/e2e.sh to build and test it.")
    elif platform.system() == "Darwin" and not shutil.which("sandbox-exec"):
        add("learn-sandbox", "mention", "The learn app is paused; sandbox-exec is missing, so its tutor shell stays off.", "None needed while it is paused.")
    tools = context.tool_status()
    if not tools["cc-check"]:
        add("toolchain-cc-check", "route", "cc-check is not in the npm cache.", "Run setup.", "setup")
    wants_formal = bool(data) and any((cl.get("tier_target") or 0) >= 4 for cl in data["claims"]) or bool(data) and any("formal" in v for v in data["verifiers"])
    for name in ("lean", "lake", "java", "tla2tools", "apalache"):
        if not tools[name]:
            add(f"toolchain-{name}", "mention",
                f"{name} is not installed." + (" A claim targets tier 4 or 5." if wants_formal else " Only formalize needs it."),
                "Install it yourself when you formalize. understando does not install toolchains.")
    for r in routes.resolve_all():
        if r.get("defer"):
            continue
        if r["use"] == "missing":
            add(f"skill-{r['skill']}", "route", f"The required skill {r['skill']} is not installed ({r['for']}).", "Install it.", "setup")
        elif r["use"] == "adapted":
            add(f"skill-{r['skill']}", "mention", f"The optional skill {r['skill']} is not installed ({r['for']}). understando uses its adapted copy {r['path']}.",
                "Install the original to route there, or keep the adapted copy.")
        elif r["use"] == "built-in":
            add(f"skill-{r['skill']}", "mention", f"The optional skill {r['skill']} is not installed ({r['for']}). understando uses its built-in rule.",
                "Install it to route there, or keep the built-in rule.")
        elif r.get("drift"):
            add(f"adapted-drift-{r['skill']}", "mention", f"The adapted copy is older than the installed original: {r['drift']}.",
                "Compare the two, and update the adapted copy under references/adapted/.")
    if data and c.repo:
        for where, a_, b_ in (("the PR", data["base"], data["head"]),
                              ("the ready branch", data["head"], (data.get("ready") or {}).get("head"))):
            if not b_:
                continue
            gone = cc_deleted(c.repo, a_, b_)
            if gone:
                add("cc-deleted" + ("-ready" if "ready" in where else ""), "mention",
                    f"{where} deletes a @cc contract comment: " + "; ".join(gone[:5]),
                    "Restore the contract, or record why it goes. trim and the comment cleanup keep each @cc comment.")
        for v in data["verifiers"]:
            imp = v.get("import")
            if not imp:
                continue
            check = importers.check(imp["kind"], Path(imp["path"]))
            if imp.get("status") == "stale" or not check["ok"] or check.get("sha256") != imp.get("sha256"):
                why = imp.get("detail") if imp.get("status") == "stale" else (check["detail"] if not check["ok"] else "the file changed after the import")
                add(f"import-stale-{v['id']}", "mention", f"{v['id']}: the imported {imp['kind']} evidence is stale: {why}.",
                    "Import it again with `understando import`; it backs nothing until then.")
    home = Path(os.environ.get("HOME", str(Path.home())))
    for d in LINK_HOMES:
        link = home / d / "understando"
        if not (link.is_symlink() and Path(os.readlink(link)).resolve() == tm.ROOT.resolve()):
            add(f"link-{d.split('/')[0].lstrip('.')}", "route", f"{link} is not a link to {tm.ROOT}.", "Run setup.", "setup")
    if not shutil.which("understando"):
        add("cli-not-on-path", "route", "The understando command is not on PATH.", "Run setup.", "setup")
    return out, fixed


def main(c: context.Ctx, argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="understando doctor", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--pr-head")
    args = ap.parse_args(argv)
    found, fixed = findings(c, args.pr_head)
    moved = []
    if args.fix and fixed is not None:
        tm.save(fixed, c.map)
        moved.append("wrote the verdicts again")
        found = [f for f in found if f["id"] != "stale-verdicts"]
    lines = [] if found else ["doctor: no findings."]
    for sev in ("auto", "mention", "route"):
        group = [f for f in found if f["severity"] == sev]
        if group:
            lines.append(f"{sev}:")
            lines += [f"  {f['id']}: {f['summary']} Fix: {f['fix']}" + (f" Verb: understando {f['verb']}" if f.get("verb") else "") for f in group]
    if moved:
        lines.append("fixed: " + "; ".join(moved))
    context.emit(c, {"findings": found, "fixed": moved}, "\n".join(lines))
    return 0
