"""understando doctor: drift and setup findings. Each finding has a severity that says what to do.

    understando doctor [--json] [--fix] [--pr-head SHA]

  auto     no decision needed: --fix applies it, and the report says what moved
  mention  the user must know; the finding offers a fix
  route    a verb closes it; the finding names the verb, and the user starts it

Checks: schema drift and stale stored verdicts; a trust map behind the PR head; a proof or a
model older than the code it covers (the drift gate); the Artifacture runtime path; the learn
sandbox (the learn app is paused); missing toolchains (java from $JAVA_HOME or Homebrew's openjdk
without a PATH edit); run output that a git repo tracks, and a run folder inside a git repo;
the visual-explainer runtime (ve_runtime in ~/.understando/config.toml) and its parts; routed skills (missing, or newer than the
adapted copy); a deleted @cc contract comment; stale imported evidence; the skill links; pasted
code in the explainer input; a code anchor that resolves to no place, or to more than one, at the
map head, the ready branch tip or --pr-head (scripts/coderef.py).
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
import coderef  # noqa: E402
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


def newer_heads(repo: Path, data: dict, explicit_head: str | None) -> list[tuple[str, str]]:
    """(name, sha) of the map head, the ready branch tip and an explicit PR head, each once."""
    out = [("the map head", data["head"])]
    ready = (data.get("ready") or {}).get("head")
    if not ready:
        tip = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "-q", f"refs/heads/understando/{data.get('pr')}-ready"],
                             capture_output=True, text=True).stdout.strip()
        ready = tip or None
    if ready:
        out.append(("the ready branch", ready))
    if explicit_head:
        out.append(("the PR head", explicit_head))
    seen, keep = set(), []
    for name, sha in out:
        if sha not in seen:
            seen.add(sha)
            keep.append((name, sha))
    return keep


def code_ref_findings(repo: Path, data: dict, extra: dict, explicit_head: str | None) -> list[tuple]:
    """Pasted code in the inputs of the explainer, and anchors that drift: on a head, an anchor
    that resolves to no place or to more than one routes to map."""
    out = []
    # The export guards the explainer MDX itself (the visual-explainer no-hand-copy guard).
    pasted = coderef.pasted(repo, data["head"], coderef.guard_inputs(data, extra, []))
    if pasted:
        out.append(("pasted-code", "route", f"The explainer input holds pasted code: {pasted[0]}" + (f" (and {len(pasted) - 1} more)" if len(pasted) > 1 else ""),
                    "Replace the pasted code with a code ref; preview it with `understando snippet`.", "map"))
    anchors = [(w, r) for w, r in coderef.walk_refs(data, extra) if coderef.is_anchor(r)]
    anchors += [(w, coderef.anchor_ref(e)) for _, w, e in coderef.walk_edits(data) if coderef.is_anchor(e)]
    for name, sha in newer_heads(repo, data, explicit_head):
        broken = []
        for where, ref in anchors:
            try:
                coderef.resolve(repo, sha, ref)
            except coderef.AnchorError as exc:
                broken.append(f"{where}: {exc}")
        if broken:
            out.append((f"anchor-drift-{sha[:10]}", "route", f"At {name} ({sha[:10]}), {len(broken)} code anchors do not resolve once: " + "; ".join(broken[:3]),
                        "Write the anchors again for the new code, then build again.", "map"))
    return out


VECTOR_FILE = ("vectors",)
GENERATOR_SUFFIXES = (".py", ".lean", ".tla", ".sh", ".mjs", ".js", ".ts")


def vector_findings(repo: Path, ref: str, run_tlc: bool) -> list[dict]:
    """Each committed vectors file under a formal/ folder needs a committed generator: the
    understando formal_tlc.py header (spec, cfg, stop rule), or a generator file next to it. With
    run_tlc, each formal_tlc.py file is generated again and compared byte for byte."""
    import ci
    out = []
    files = [p for p in ci.ls(repo, ref, ".") if "/formal/" in f"/{p}" and any(w in p.rsplit("/", 1)[-1].lower() for w in VECTOR_FILE)
             and p.endswith((".json", ".jsonl"))]
    for f in files:
        d, name = f.rsplit("/", 1)
        text = ci.show(repo, ref, f) or ""
        head = ci.vectors_header(text)
        if head:
            missing = [x for x in (head["spec"], head["cfg"]) if ci.show(repo, ref, f"{d}/{x}") is None]
            if missing:
                out.append({"id": f"vectors-inputs-{name}", "severity": "route",
                            "summary": f"{f} names {', '.join(missing)}, which is not committed: nobody can generate the vectors again.",
                            "fix": "Commit the spec and the cfg next to the vectors.", "verb": "formalize"})
            continue
        siblings = [p for p in ci.ls(repo, ref, d) if p != f and p.endswith(GENERATOR_SUFFIXES)
                    and ("vector" in p.rsplit("/", 1)[-1].lower() or name in (ci.show(repo, ref, p) or ""))]
        if not siblings:
            out.append({"id": f"vectors-no-generator-{name}", "severity": "route",
                        "summary": f"{f} is committed, but no committed generator writes it. A reviewer cannot generate it again.",
                        "fix": "Generate it with `formal_tlc.py vectors` (TLA+), or commit the generator next to it.", "verb": "formalize"})
    if run_tlc and files:
        prof = ci.formal_commands(repo, ref, sorted({f.split("/formal/")[0] if "/formal/" in f else "." for f in files}))
        import tempfile
        with tempfile.TemporaryDirectory(prefix="understando-vectors-") as tmp:
            root = Path(tmp)
            for d in sorted({x["cwd"] for x in prof if x["tool"] == "tlc-vectors"}):
                ci.extract(repo, ref, d, root)
            for x in (x for x in prof if x["tool"] == "tlc-vectors"):
                res = subprocess.run(x["argv"], cwd=root / x["cwd"], capture_output=True, text=True, timeout=1800)
                if res.returncode == 1:
                    out.append({"id": f"vectors-drift-{Path(x['generates']).name}", "severity": "route",
                                "summary": f"{x['generates']} differs from what formal_tlc.py vectors writes at {ref[:10]}.",
                                "fix": "Generate it again with the command in ci.json, commit it on the ready branch, then check it again.",
                                "verb": "formalize"})
                elif res.returncode:
                    out.append({"id": f"vectors-error-{Path(x['generates']).name}", "severity": "mention",
                                "summary": f"formal_tlc.py vectors did not finish for {x['generates']} (exit {res.returncode}).",
                                "fix": "Check the TLC toolchain."})
    return out


RUN_MARKERS = ("trust-map.json", "journal.jsonl", "discover.json", "refs.resolved.json", "ve-report.json",
               "explain.stamp.json", "understando.toml", "decisions.tsv")


def tracked_run_output(repo: Path, own: bool = False) -> list[dict]:
    """Run output that a git repo tracks: understando's own runs/ folder, or a run file (by name) in
    any repo. The fixture of understando's tests is not run output."""
    out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, text=True)
    if out.returncode != 0:
        return []
    files = [f for f in out.stdout.split("\0") if f]
    hits = [f for f in files if f.rsplit("/", 1)[-1] in RUN_MARKERS or (own and f.startswith("runs/"))]
    if own:
        hits = [f for f in hits if not f.startswith(("tests/", "schema/"))]
    if not hits:
        return []
    where = "understando's own repo" if own else f"the reviewed repo {repo}"
    fix = ("Untrack it with `git rm -r --cached runs/`, keep runs/ in .gitignore, and keep run state under ~/.understando/runs."
           if own else "Untrack it with `git rm --cached` on a branch the owner reviews; understando keeps run state under ~/.understando/runs.")
    return [{"id": "run-output-tracked" + ("-own" if own else ""), "severity": "route",
             "summary": f"{where} tracks {len(hits)} run-output files: " + ", ".join(hits[:3]) + (" ..." if len(hits) > 3 else ""),
             "fix": fix, "verb": "setup"}]


def findings(c: context.Ctx, explicit_head: str | None, formal: bool = False) -> tuple[list[dict], dict | None]:
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
    import config
    ve = config.ve_runtime()
    if ve and config.ve_missing(ve):
        add("runtime-missing", "mention", f"The visual-explainer runtime {ve} lacks {', '.join(config.ve_missing(ve))}.",
            "Point ve_runtime in ~/.understando/config.toml at a complete Artifacture checkout (run `npm ci` in it).", "setup")
    elif not ve:
        add("runtime-missing", "mention", f"No visual-explainer runtime: ve_runtime is not set in {config.global_path()}.",
            "Run setup; it asks once.", "setup")
    for f in tracked_run_output(tm.ROOT, own=True) + (tracked_run_output(c.repo) if c.repo else []):
        out.append(f)
    if c.run:
        refusal = context.refuse_run_write(c.run, c.repo)
        if refusal:
            add("run-in-git", "route", refusal.removeprefix("refuse: ").split(". ")[0] + ", so no verb writes to it.",
                f"Copy the run folder under {config.runs_root()}, outside every git repo, and use that copy.", "setup")
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
        extra = tm.load(c.run / "explain.json") if (c.run / "explain.json").is_file() else {}
        for f in code_ref_findings(c.repo, data, extra, explicit_head):
            add(*f)
        for v in data["verifiers"]:
            imp = v.get("import")
            if not imp:
                continue
            check = importers.check(imp["kind"], Path(imp["path"]))
            if imp.get("status") == "stale" or not check["ok"] or check.get("sha256") != imp.get("sha256"):
                why = imp.get("detail") if imp.get("status") == "stale" else (check["detail"] if not check["ok"] else "the file changed after the import")
                add(f"import-stale-{v['id']}", "mention", f"{v['id']}: the imported {imp['kind']} evidence is stale: {why}.",
                    "Import it again with `understando import`; it backs nothing until then.")
    if c.repo:
        import ci
        import config
        import lock
        import repoinfo
        cfg = config.for_repo(c.repo)
        out += config.findings(cfg, c.repo)
        if c.run and c.run.is_dir():
            prof = ci.load(c.run)
            if prof and not ci.approved(prof):
                add("ci-unapproved", "mention", "The CI profile (ci.json) is not approved, so probe, close and trim refuse to run.",
                    "Show `understando ci` to the user; after a yes, the user runs `understando ci --approve`.")
            stale = [h for h in lock.read(c.run) if not lock.alive(int(h["pid"]))]
            if stale:
                add("lock-stale", "auto", f"{len(stale)} lock entries name a process that ended.", "The next writing verb removes them.")
        if data:
            branch = cfg["ready_branch"].format(pr=data.get("pr"))
            ref = repoinfo.rev(c.repo, f"refs/remotes/origin/{branch}") or repoinfo.rev(c.repo, f"refs/heads/{branch}") or data["head"]
            wt = repoinfo.worktree_of(c.repo, branch)
            remote = repoinfo.rev(c.repo, f"refs/remotes/origin/{branch}")
            if wt and remote:
                behind = subprocess.run(["git", "-C", str(wt), "rev-list", "--count", f"HEAD..{remote}"], capture_output=True, text=True).stdout.strip()
                if behind and behind != "0":
                    add("ready-behind", "route", f"The worktree {wt} is {behind} commits behind origin/{branch}.",
                        "Pull it with --no-rebase before any edit.", "review")
            for f in vector_findings(c.repo, ref, formal):
                out.append(f)
            owners = cfg.get("deferred_owners") or {}
            for i in data.get("invariants", []):
                if i.get("status") == "proposed" and i.get("deferred") and not (i.get("owner") or owners.get(i["id"])):
                    add(f"deferred-no-owner-{i['id']}", "mention", f"The deferred invariant {i['id']} has no owner.",
                        "Name the owner in the discover answer, or in deferred_owners of understando.toml.")
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
    ap.add_argument("--formal", action="store_true", help="also generate each formal_tlc.py vectors file again (runs TLC)")
    args = ap.parse_args(argv)
    found, fixed = findings(c, args.pr_head, args.formal)
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
