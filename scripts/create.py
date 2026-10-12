"""understando create: a project-local verification skill with a feature map, and a Verifier section
for each feature: the surface, the bar, and the verifiers that meet it.

    understando create                         interview the repo: print what it finds (step 1)
    understando create --spec FILE [--patch OUT] [--yes]   write the skill to understando/verify-<app> (step 2, 3)
    understando create --check                 check the shape of the skill on the branch
    understando create --prove FEATURE [--yes] prove the skill end to end on one feature (step 4)
    understando create --verifier [--yes]      write the Verifier sections again from the store

The skill goes to .agents/skills/verify-<app>/, with a relative symlink .claude/skills/verify-<app>.
It holds SKILL.md (Launch, Doctor, Drive, Evidence, Cleanup, Helpers), helpers/verify, and
features/README.md with one file per feature (references/verify-skill.md has the shape). This is the
one place where understando writes into a repo: a commit on the branch understando/verify-<app>, or
a patch file, after the user's yes. A repo that has a verify skill already (for example from
create-verification-skill) gets its feature files extended, not a second skill.

--prove runs the skill's own steps in a scratch copy of the branch: launch, doctor, drive ONE
feature with its evidence in the run folder, cleanup, then it checks that the evidence still
exists, and that the feature's control makes the drive fail. A skill that never ran is a draft.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import ops  # noqa: E402
import run_control  # noqa: E402
import store  # noqa: E402
import strength  # noqa: E402

SECTIONS = ("Launch", "Doctor", "Drive", "Evidence", "Cleanup", "Helpers")
FEATURE_H2 = ("Sub-features", "How to get to it (user POV)", "Driving it with", "Gotchas", "Verifier")
START, END = "<!-- understando:verifier:start -->", "<!-- understando:verifier:end -->"
HOMES = (".agents/skills", ".cursor/skills", ".claude/skills")
BAR_TEXT = {
    "frontend": ["A real-browser e2e that drives the user path, with a recorded video and screenshots as evidence.",
                 "A unit or component test is below the bar."],
    "backend": ["**Formal:** Lean or TLA+ with conformance against the real code, for a risky invariant (`understando formalize`).",
                "**Code Contracts:** a `@cc` contract states the invariant, and a check with a control proves it. `cc-check format` checks the contract.",
                "**Types, import rules and property tests,** for wiring."],
    "llm": ["A recorded eval with a frozen judge or labels.", "A degraded variant of the prompt or the model must score worse."],
    "other": ["A check that a control can make fail."],
}
EVIDENCE = {"frontend": ["*.webm", "*.png"], "backend": ["*.txt"], "llm": ["*.json"], "other": ["*"]}


def branch_of(app: str) -> str:
    return f"understando/verify-{app}"


def skill_dir(app: str) -> str:
    return f".agents/skills/verify-{app}"


def existing(repo: Path, ref: str) -> list[str]:
    """The verify skills at a commit: <home>/verify-*/SKILL.md (a symlinked folder counts once)."""
    files = store.git(repo, "ls-tree", "-r", "--name-only", ref, check=False).split()
    found = sorted({f.rsplit("/", 1)[0] for f in files if re.match(r"^(\.agents|\.cursor|\.claude)/skills/verify-[^/]+/SKILL\.md$", f)})
    return [f for f in found if not f.startswith(".claude/") or f.replace(".claude/", ".agents/", 1) not in found]


# ---- step 1: the interview -------------------------------------------------------------------------

def interview(repo: Path) -> dict:
    import testcmd
    import toolprobe
    files = store.git(repo, "ls-files").split()
    text = lambda p: (repo / p).read_text(encoding="utf-8", errors="replace") if (repo / p).is_file() else ""  # noqa: E731
    surfaces = []
    pkg = text("package.json")
    if re.search(r'"(react|vue|svelte|next|vite|@angular/core|solid-js)"', pkg) or any(f.endswith((".tsx", ".jsx", ".vue", ".svelte")) for f in files):
        surfaces.append({"surface": "web", "evidence": "a UI framework in package.json, or UI source files"})
    py = [f for f in files if f.endswith(".py")]
    mains = [f for f in py if f.endswith("__main__.py")]
    if mains or "[project.scripts]" in text("pyproject.toml") or any(f.startswith("bin/") for f in files):
        surfaces.append({"surface": "cli", "evidence": ", ".join(mains[:3]) or "bin/ or [project.scripts]"})
    apis = [f for f in py if re.search(r"\b(FastAPI|Flask|APIRouter)\(", text(f))]
    if apis or re.search(r'"express"', pkg):
        surfaces.append({"surface": "api", "evidence": ", ".join(apis[:3]) or "express in package.json"})
    llm = [f for f in py if re.search(r"^\s*(import|from) (openai|anthropic)\b", text(f), re.M)]
    if llm:
        surfaces.append({"surface": "llm", "evidence": ", ".join(llm[:3])})
    if not surfaces:
        surfaces.append({"surface": "library", "evidence": "no UI, CLI or service entry point"})
    commands = []
    for f in py:
        for m in re.finditer(r"add_parser\(\s*[\"']([\w-]+)[\"']", text(f)):
            commands.append({"feature": m.group(1), "where": f})
        for m in re.finditer(r"@\w+\.(get|post|put|delete|patch)\(\s*[\"']([^\"']+)", text(f)):
            commands.append({"feature": f"{m.group(1).upper()} {m.group(2)}", "where": f})
    run = []
    if mains:
        run += [f"python3 -m {m.rsplit('/', 1)[0].replace('/', '.')}" for m in mains]
    for script in ("dev", "start", "serve"):
        if f'"{script}"' in pkg:
            run.append(f"npm run {script}")
    harness = [f for f in files if re.search(r"(playwright|cypress)\.config\.|\.spec\.(ts|js)$|e2e/", f)][:5]
    name = re.sub(r"[^a-z0-9-]", "-", repo.name.lower()).strip("-") or "app"
    original = toolprobe.find_skill("create-verification-skill")
    return {"app": name, "existing": existing(repo, "HEAD"), "surfaces": surfaces, "features": commands[:12],
            "run": run, "harness": harness, "tests": testcmd.candidates(repo),
            "original_skill": str(original) if original else None,
            "next": "Write the spec (references/verify-skill.md), then run `understando create --spec FILE`."}


# ---- step 2 and 3: render the skill and the feature map ----------------------------------------------

def bullets(items: list[str]) -> list[str]:
    return [f"- {x}" for x in items]


def render_skill(spec: dict) -> str:
    app = spec["app"]
    sk = skill_dir(app)
    s = lambda k: spec.get(k) or {}  # noqa: E731
    lines = ["---", f"name: verify-{app}", f"description: \"{spec['description']}\"", "---", "",
             f"# verify-{app}", "", spec.get("intro") or f"Drive {app} the way a user does, and keep the proof. Read features/README.md, then the file of the feature.", "",
             "## Launch", "", s("launch").get("text", ""), "", f"Run `{sk}/helpers/verify launch`. Ready when: {s('launch').get('ready', 'the command exits 0')}.", "",
             "## Doctor", "", s("doctor").get("text", ""), "", f"Run `{sk}/helpers/verify doctor` first, and again after any surprise. It only reads.", "",
             "## Drive", "", s("drive").get("text", ""), "", f"Run `{sk}/helpers/verify drive <feature>`. Each feature file names its exact steps.", "",
             "## Evidence", "", s("evidence").get("text", ""), "",
             "- Exercise the real user path, not internal setters or test-only endpoints.",
             "- Capture the action and the resulting state, not only the final screen.",
             "- Verify side effects (files written, rows inserted, messages sent) next to what is visible.",
             "- The drive writes its proof to `$VERIFY_EVIDENCE_DIR` (default: a folder under `$TMPDIR`). Cleanup never removes it.", "",
             "## Cleanup", "", s("cleanup").get("text", ""), "",
             f"Run `{sk}/helpers/verify cleanup`. It stops only what launch started, and it keeps the evidence.", "",
             "## Helpers", "",
             f"- `{sk}/helpers/verify launch | doctor | drive <feature> | cleanup | prove <feature>`: `prove` runs launch, doctor, drive and cleanup in that order, and cleanup runs also on a failure.",
             "- The script is executable. Run it from any folder: it finds the repo root with git.", ""]
    return "\n".join(lines)


def render_helper(spec: dict) -> str:
    h = spec.get("helper") or {}
    app = spec["app"]
    drive = h.get("drive") or {}
    cases = "\n".join(f"      {fid})\n{indent(body, 8)}\n        ;;" for fid, body in drive.items())
    return f"""#!/usr/bin/env bash
# verify-{app}: launch | doctor | drive <feature> | cleanup | prove <feature>. Written by understando create.
# The drive writes its proof to $VERIFY_EVIDENCE_DIR. Cleanup never removes the evidence.
set -euo pipefail
ROOT="$(git -C "$(dirname "${{BASH_SOURCE[0]}}")" rev-parse --show-toplevel)"
EVIDENCE="${{VERIFY_EVIDENCE_DIR:-${{TMPDIR:-/tmp}}/verify-{app}-evidence}}"
STATE="${{VERIFY_STATE_DIR:-${{TMPDIR:-/tmp}}/verify-{app}-state}}"
mkdir -p "$EVIDENCE" "$STATE"
cd "$ROOT"
usage() {{ echo "usage: $0 launch | doctor | drive <feature> | cleanup | prove <feature>" >&2; exit 2; }}
launch() {{
{indent(h.get("launch") or ":", 2)}
}}
doctor() {{
{indent(h.get("doctor") or ":", 2)}
}}
cleanup() {{
{indent(h.get("cleanup") or ":", 2)}
}}
drive() {{
  case "${{1:-}}" in
{cases}
      *) echo "verify-{app}: no feature '${{1:-}}'. The features: {' '.join(drive)}" >&2; exit 2 ;;
  esac
}}
case "${{1:-}}" in
  launch) launch ;;
  doctor) doctor ;;
  drive) shift; drive "$@" ;;
  cleanup) cleanup ;;
  prove) shift; trap cleanup EXIT; launch; doctor; drive "$@" ;;
  *) usage ;;
esac
"""


def indent(text: str, n: int) -> str:
    return "\n".join((" " * n + line) if line.strip() else "" for line in text.strip("\n").splitlines())


def render_readme(spec: dict, files: list[tuple[str, str]]) -> str:
    app = spec["app"]
    lines = [f"# {app} verification map", "",
             "This folder is the maintained source for verifying the user-facing behaviour of "
             f"{app}. Read this index first, then use the file of the feature as the recipe.", "",
             "## Baseline preconditions", ""] + bullets(spec.get("preconditions") or [f"Run `{skill_dir(app)}/helpers/verify doctor` and require a pass."]) + [
             "", "## Proof and skip reporting", "",
             "- Capture the user action and the resulting state, not only the final screen.",
             "- Record the feature ID and the entry point with every artifact.",
             "- Report an unreachable path with the attempted command and the unmet precondition.",
             "- Do not report a skipped entry point as verified through a different path.", "",
             "## Feature entry contract", "",
             "Each feature file starts with an H1 title and one paragraph about the user-visible behaviour. Then come the H2 sections "
             "`Sub-features`, `How to get to it (user POV)`, `Driving it with <harness>` and `Gotchas`, in this order. "
             "The last H2, `Verifier`, names the surface of the feature, its bar and the verifiers that meet it. "
             "understando writes it from its evidence store; do not edit it by hand.", "",
             "## Features", ""]
    lines += [f"- [{name}](./{fname}) {summary}" for fname, name, summary in files]
    return "\n".join(lines) + "\n"


def render_feature(spec: dict, f: dict, verifier: str) -> str:
    harness = (spec.get("drive") or {}).get("harness") or f"verify-{spec['app']}"
    lines = [f"# {f['name']}", "", f["summary"], "", "## Sub-features", ""]
    lines += [f"- `{x['id']}` {x['text']}" for x in f.get("sub_features") or []]
    lines += ["", "## How to get to it (user POV)", ""] + bullets(f.get("entry_points") or [])
    lines += ["", f"## Driving it with {harness}", "", "Preconditions:", ""] + bullets(f.get("preconditions") or ["The doctor passes."]) + [""]
    for st in f.get("steps") or []:
        lines.append(f"- **{st['label']}.** {st['action']} Run `{st['command']}`. {st['result']}")
    lines.append(f"- **Proof.** Run `{skill_dir(spec['app'])}/helpers/verify drive {f['id']}`. "
                 f"{f.get('proof') or 'It exits 0 only when the end state holds, and it writes the transcript to the evidence folder.'}")
    lines += ["", "## Gotchas", ""] + bullets(f.get("gotchas") or ["None known yet."])
    lines += ["", START, verifier, END, ""]
    return "\n".join(lines)


def render_verifier(data: dict, fid: str) -> str:
    """The Verifier section of one feature, from the evidence store."""
    feat = store.need(data, "features", fid)
    rep = strength.apply(data)
    surface = feat["surface"]
    lines = ["## Verifier", "", f"- **Surface:** {surface}.", "- **Bar:**"] + [f"  - {x}" for x in BAR_TEXT[surface]]
    invs = [i for i in data["invariants"] if i.get("feature") == fid and i["status"] in ("accepted", "proposed")]
    lines.append("- **Invariants:**" + ("" if invs else " none yet. Run `understando discover --feature " + fid + "`."))
    for i in invs:
        who = "the user's" if i["author"] == "user" and i["status"] == "accepted" else "agent-picked, not accepted by the user yet"
        lines.append(f"  - `{i['id']}` ({who}): {i['text']}")
    by_check = {}
    for k in data["controls"]:
        by_check.setdefault(k["check"], []).append(k)
    claims = [c for c in rep["claims"] if c["feature"] == fid]
    meet, below, dead = [], [], []
    for v in [x for x in data["checks"] if x.get("feature") == fid]:
        ks = by_check.get(v["id"], [])
        caught = [k["id"] for k in ks if strength.outcome(v, k) == "caught"]
        cmd = " ".join((v.get("command") or {}).get("argv", [])) or (v.get("recorded") or {}).get("source", "recorded")
        ctl = "; ".join(f"`{k['id']}` {k['kind']}: {(k.get('description') or k['edits'][0].get('op', '')).rstrip('.')}" for k in ks) or "none yet"
        row = f"  - `{v['id']}` {v.get('name', v['kind'])} ({v['kind']}, rung {store.ladder(v)}): `{cmd}`. Controls: {ctl}."
        if v["state"] in ("cannot-fail", "failing", "broken"):
            dead.append(row + f" It is **{v['state']}**: it does not count.")
            continue
        ok = v["state"] == "proven" and any(strength.meets_bar(data, surface, c["risky"], v, ks)[0] for c in claims) if claims else \
            v["state"] == "proven" and strength.meets_bar(data, surface, False, v, ks)[0]
        state = f"proven: {', '.join(caught)} made it fail" if v["state"] == "proven" else f"{v['state']}: no control made it fail yet"
        (meet if ok else below).append(row + f" {state[0].upper() + state[1:]}.")
    lines.append("- **Verifiers that meet the bar:**" + ("" if meet else " none yet."))
    lines += meet
    if below:
        lines += ["- **Verifiers below the bar or not proven yet:**"] + below
    if dead:
        lines += ["- **Verifiers that do not count:**"] + dead
    lines += ["- **Rule:** every verifier has a control (a planted bug, a mutant or a degraded variant) that must make it fail. "
              "A verifier that cannot fail does not count.",
              f"- **Run again:** `understando probe --feature {fid} --yes`, and `understando probe mutate --feature {fid} --yes`."]
    return "\n".join(lines)


def set_verifier(text: str, block: str) -> str:
    if START in text and END in text:
        return text[:text.index(START)] + START + "\n" + block + "\n" + text[text.index(END):]
    return text.rstrip("\n") + "\n\n" + START + "\n" + block + "\n" + END + "\n"


def register(data: dict, spec: dict, skill: str, tip: str | None) -> None:
    """The features of the spec, and the drive of each one as an e2e check with its control."""
    for f in spec["features"]:
        feat = store.find(data, "features", f["id"])
        row = {"id": f["id"], "name": f["name"], "surface": f.get("surface", "other"), "file": f"{skill}/features/{f['id']}.md",
               **({"paths": f["paths"]} if f.get("paths") else {})}
        if feat:
            row["drive"] = feat.get("drive")
            feat.clear()
            feat.update({k: x for k, x in row.items() if x})
        else:
            data["features"].append(row)
            feat = row
        if not (spec.get("helper") or {}).get("drive", {}).get(f["id"]):
            continue
        v = store.find(data, "checks", feat.get("drive"))
        if not v:
            v = {"id": store.next_id(data, "checks"), "feature": f["id"], "kind": "e2e", "name": f"the drive of {f['name'].lower()}"}
            data["checks"].append(v)
            feat["drive"] = v["id"]
        v["command"] = {"argv": ["bash", f"{skill}/helpers/verify", "prove", f["id"]]}
        v["evidence"] = {"require": f.get("evidence") or EVIDENCE.get(feat["surface"], ["*"])}
        if tip:
            v["at"] = tip
        if f.get("control") and not any(k["check"] == v["id"] for k in data["controls"]):
            data["controls"].append({"id": store.next_id(data, "controls"), "check": v["id"], "kind": "planted",
                                     "description": f["control"].get("description", "A planted bug in the feature's code."),
                                     "edits": f["control"]["edits"], "expect": {"status": "red"}})


def write_tree(root: Path, spec: dict, data: dict, extend: str | None) -> list[str]:
    """Write the skill into a checkout. Returns the written paths."""
    app = spec["app"]
    sk = extend or skill_dir(app)
    base = root / sk
    out = []

    def put(rel: str, body: str, mode: int | None = None) -> None:
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        if mode:
            p.chmod(mode)
        out.append(f"{sk}/{rel}")

    if not extend:
        put("SKILL.md", render_skill(spec))
    if spec.get("helper") and not (base / "helpers" / "verify").exists():
        put("helpers/verify", render_helper(spec), 0o755)
        if extend and "helpers/verify" not in (base / "SKILL.md").read_text(encoding="utf-8"):
            put("SKILL.md", (base / "SKILL.md").read_text(encoding="utf-8").rstrip("\n") + "\n\n## Helpers (understando)\n\n"
                f"- `{sk}/helpers/verify launch | doctor | drive <feature> | cleanup | prove <feature>`.\n")
    elif spec.get("helper") and not extend:
        put("helpers/verify", render_helper(spec), 0o755)
    index = []
    for f in spec["features"]:
        p = base / "features" / f"{f['id']}.md"
        block = render_verifier(data, f["id"])
        body = set_verifier(p.read_text(encoding="utf-8"), block) if p.is_file() else render_feature(spec, f, block)
        put(f"features/{f['id']}.md", body)
        index.append((f"{f['id']}.md", f["name"], f["summary"].split(". ")[0].rstrip(".") + "."))
    readme = base / "features" / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        add = [f"- [{n}](./{fn}) {s}" for fn, n, s in index if f"./{fn})" not in text]
        if add:
            put("features/README.md", text.rstrip("\n") + "\n" + "\n".join(add) + "\n")
    else:
        put("features/README.md", render_readme(spec, index))
    if not extend:
        link = root / ".claude" / "skills" / f"verify-{app}"
        if not link.exists() and not link.is_symlink():
            link.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(f"../../{sk}", link)
            out.append(f".claude/skills/verify-{app} -> ../../{sk}")
    return out


def write(c: store.Ctx, spec_path: str | None, patch: str | None, verifier_only: bool) -> int:
    repo = c.need_repo()
    data = c.open_data()
    if spec_path:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
        (c.run / "create.spec.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    else:
        sp = c.run / "create.spec.json"
        if not sp.is_file():
            store.fail("create: no spec; run `understando create --spec FILE` first", 2)
        spec = json.loads(sp.read_text(encoding="utf-8"))
    app = spec["app"]
    data["app"] = app
    branch = branch_of(app)
    tip = ops.branch_tip(repo, branch)
    start = tip or store.git(repo, "rev-parse", "HEAD")
    found = existing(repo, start)
    # Our own skill (on the branch, or merged) is updated in place. Another verify skill (for example
    # from create-verification-skill) is extended: understando adds feature files and Verifier sections.
    other = [x for x in found if x != skill_dir(app)]
    extend = None if skill_dir(app) in found or not other else (next((x for x in other if x.endswith(f"verify-{app}")), other[0]))
    sk = extend or skill_dir(app)
    register(data, spec, sk, None)
    preview = [f"{sk}/SKILL.md", f"{sk}/helpers/verify", f"{sk}/features/README.md"] + [f"{sk}/features/{f['id']}.md" for f in spec["features"]]
    where = f"a patch at {patch}" if patch else f"the branch {branch} ({'a new commit on it' if tip else 'a new branch from HEAD'})"
    if not c.yes:
        msg = [f"create {'extends' if extend else 'writes'} the verify skill {sk} in {where}:"] + [f"  {p}" for p in preview]
        msg += ["Your branches and your commits do not change. Write it? Repeat the same command with --yes."]
        store.emit(c, {"confirm": {"what": "create", "writes": preview, "where": where}}, "\n".join(msg))
        return 0
    with ops.scratch_clone(repo) as (clone, wt):
        written: list[str] = []
        new = ops.commit_on(clone, wt, start, f"verify-{app}: {'extend the' if extend else 'add the'} verify skill and its feature map"
                            if not verifier_only else f"verify-{app}: write the Verifier sections again",
                            lambda root: written.extend(write_tree(root, spec, data, extend)))
        if new is None:
            store.emit(c, {"written": [], "branch": branch}, "create: nothing changed")
            return 0
        if patch:
            diff = ops.git(clone, "format-patch", "--stdout", f"{start}..{new}")
            Path(patch).write_text(diff + "\n", encoding="utf-8")
        else:
            ops.fast_forward(clone, repo, branch, new)
    if not patch:
        data["ready"] = {"branch": branch, "head": new}
        for v in data["checks"]:
            if v["id"] in {f.get("drive") for f in data["features"]}:
                v["at"] = new
    data["skill"] = sk
    data["head"] = store.git(repo, "rev-parse", "HEAD")
    c.save(data)
    lines = [f"create: {'extended' if extend else 'wrote'} {sk} " + (f"as the patch {patch}" if patch else f"on {branch} at {new[:10]}")] + [f"  {p}" for p in written]
    if not patch:
        lines.append(f"Next: understando create --check, then understando create --prove {spec['features'][0]['id']}")
    store.emit(c, {"written": written, "branch": None if patch else branch, "commit": new, "skill": sk}, "\n".join(lines))
    return 0


# ---- the shape check ---------------------------------------------------------------------------

def check_shape(repo: Path, ref: str, sk: str) -> list[str]:
    show = lambda p: subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{p}"], capture_output=True, text=True).stdout  # noqa: E731
    problems = []
    body = show(f"{sk}/SKILL.md")
    if not body.startswith("---\n") or not re.search(r"(?m)^name: verify-", body) or not re.search(r"(?m)^description: ", body):
        problems.append("SKILL.md has no frontmatter with name and description: the skill never registers")
    for s in SECTIONS:
        if not re.search(rf"(?m)^## {s}\b", body):
            problems.append(f"SKILL.md has no {s} section")
    if re.search(r"\{\{|\bTODO\b|<placeholder>|TBD", body):
        problems.append("SKILL.md holds a placeholder")
    files = store.git(repo, "ls-tree", "-r", "--name-only", ref, "--", f"{sk}/").split()
    helpers = [f for f in files if f.startswith(f"{sk}/helpers/")]
    for h in helpers:
        mode = store.git(repo, "ls-tree", ref, "--", h).split()[0]
        if mode != "100755":
            problems.append(f"{h} is not executable")
        if h.split(f"{sk}/", 1)[1] not in body:
            problems.append(f"{h} is not shown in SKILL.md")
    readme = show(f"{sk}/features/README.md")
    feats = [f for f in files if f.startswith(f"{sk}/features/") and f.endswith(".md") and not f.endswith("README.md")]
    if not readme:
        problems.append("features/README.md is missing")
    for f in feats:
        name = f.rsplit("/", 1)[1]
        if f"./{name})" not in readme:
            problems.append(f"features/README.md does not link {name}")
        text = show(f)
        if not text.startswith("# "):
            problems.append(f"{name} does not start with an H1 title")
        h2 = re.findall(r"(?m)^## (.+)$", text)
        for want in FEATURE_H2:
            if not any(x.startswith(want) for x in h2):
                problems.append(f"{name} has no '{want}' section")
        if START not in text:
            problems.append(f"{name} has no Verifier section from understando")
    for link in re.findall(r"\]\(\./([^)]+)\)", readme):
        if f"{sk}/features/{link}" not in files:
            problems.append(f"features/README.md links {link}, which does not exist")
    link = f".claude/skills/{sk.rsplit('/', 1)[1]}"
    if sk.startswith(".agents/") and store.git(repo, "ls-tree", ref, "--", link, check=False).split()[:1] != ["120000"]:
        problems.append(f"{link} is not a symlink to {sk}")
    return problems


# ---- step 4: prove the skill -------------------------------------------------------------------

def prove(c: store.Ctx, fid: str) -> int:
    repo = c.need_repo()
    data = c.need_data()
    feat = store.need(data, "features", fid)
    v = store.need(data, "checks", feat.get("drive"))
    tip = (data.get("ready") or {}).get("head") or v.get("at") or store.git(repo, "rev-parse", "HEAD")
    sk = data.get("skill") or skill_dir(data["app"])
    helper = f"{sk}/helpers/verify"
    steps = [["bash", helper, "launch"], ["bash", helper, "doctor"], ["bash", helper, "drive", fid], ["bash", helper, "cleanup"]]
    if not store.confirm(c, f"create --prove {fid}", steps + [v["command"]["argv"]]):
        return 0
    ev = c.run / "evidence" / fid / f"prove-{store.stamp()}"
    ev.mkdir(parents=True, exist_ok=True)
    state = Path(os.environ.get("TMPDIR", "/tmp")) / f"understando-state-{os.getpid()}"
    env = {"VERIFY_EVIDENCE_DIR": str(ev), "VERIFY_STATE_DIR": str(state)}
    rows, ok = [], True
    with ops.scratch_clone(repo) as (clone, wt):
        with run_control.Worktree(clone, tip, wt, "prove") as root:
            run_control.prepare(root, data)
            try:
                for argv in steps[:3]:
                    code, out, sec = run_control.run_command(root, {"argv": argv}, None, env)
                    rows.append({"step": argv[2], "exit": code, "seconds": sec, "output_tail": run_control.tail(run_control.scrub(out, root))})
                    print(f"prove {fid}: {argv[2]}: {'ok' if code == 0 else f'FAILED (exit {code})'}")
                    if code != 0:
                        ok = False
                        break
            finally:
                code, out, sec = run_control.run_command(root, {"argv": steps[3]}, None, env)
                rows.append({"step": "cleanup", "exit": code, "seconds": sec, "output_tail": run_control.tail(out)})
                print(f"prove {fid}: cleanup: {'ok' if code == 0 else f'FAILED (exit {code})'}")
                ok = ok and code == 0
        kept = run_control.kept(ev)
        need = v.get("evidence", {}).get("require") or ["*"]
        import fnmatch
        missing = [g for g in need if not any(fnmatch.fnmatch(Path(f).name, g) for f in kept)]
        print(f"prove {fid}: evidence after cleanup: {len(kept)} files in {ev}" + (f"; MISSING {', '.join(missing)}" if missing else ""))
        ok = ok and not missing
        if ok:
            v["baseline"] = {"status": "green", "exit": 0, "ran_at": store.now(), "head": tip, "evidence": kept,
                             "output_tail": rows[2]["output_tail"] if len(rows) > 2 else ""}
        controls = [k for k in data["controls"] if k["check"] == v["id"]]
        for k in controls:
            run_control.run_one(data, k, clone, wt, commit=tip)
    caught = [k for k in controls if strength.outcome(v, k) == "caught"]
    if not controls:
        print(f"prove {fid}: the drive has no control. Add one to the spec (feature.control) and run create again: a drive that cannot fail proves nothing.")
    elif not caught:
        print(f"prove {fid}: FAILED: the drive stayed green on each control ({', '.join(k['id'] for k in controls)}). It cannot fail, so it proves nothing.")
    data["proved"] = {"feature": fid, "at": tip, "ran_at": store.now(), "steps": rows, "evidence": kept,
                      "controls": {k["id"]: (k.get("result") or {}).get("status") for k in controls}, "ok": bool(ok and caught)}
    c.save(data)
    print(f"prove {fid}: {'PASS: the skill ran end to end, the evidence survived cleanup, and the control made the drive fail.' if data['proved']['ok'] else 'FAIL'}")
    return 0 if data["proved"]["ok"] else 1


def main(c: store.Ctx, argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="understando create", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec")
    ap.add_argument("--patch", help="write a patch file instead of the branch")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--prove", metavar="FEATURE")
    ap.add_argument("--verifier", action="store_true", help="write the Verifier sections again from the store")
    args = ap.parse_args(argv)
    repo = c.need_repo()
    c.need_run()
    if args.prove:
        return prove(c, args.prove)
    if args.check:
        data = c.need_data()
        ref = (data.get("ready") or {}).get("head") or "HEAD"
        sk = data.get("skill") or skill_dir(data["app"])
        problems = check_shape(repo, ref, sk)
        store.emit(c, {"skill": sk, "at": ref, "problems": problems},
                   "\n".join([f"create --check {sk} at {ref[:10]}: " + ("the shape holds." if not problems else f"{len(problems)} problems")]
                             + [f"  - {p}" for p in problems]))
        return 1 if problems else 0
    if args.spec or args.verifier:
        return write(c, args.spec, args.patch, args.verifier)
    out = interview(repo)
    (c.run / "create.interview.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    lines = [f"create: the interview of {repo.name} (the full record is {c.run / 'create.interview.json'})",
             "surfaces: " + "; ".join(f"{s['surface']} ({s['evidence']})" for s in out["surfaces"]),
             "verify skills already here: " + (", ".join(out["existing"]) or "none"),
             "run: " + (", ".join(out["run"]) or "none found"),
             "test commands (proposals, never run without your yes): " + ("; ".join(f"`{t['command']}` ({t['source']})" for t in out["tests"]) or "none found"),
             "feature candidates: " + (", ".join(f"{f['feature']} ({f['where']})" for f in out["features"]) or "none found")]
    if out["original_skill"]:
        lines.append(f"create-verification-skill is installed ({out['original_skill']}). The user can start it; then `understando create --spec` extends its feature files.")
    lines.append(out["next"])
    store.emit(c, out, "\n".join(lines))
    return 0
