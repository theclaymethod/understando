#!/usr/bin/env python3
"""Build the explainer and the PR-body section of a trust map, through visual-explainer.

    python3 scripts/explain.py --map trust-map.json --repo <git repo> --out DIR \
        [--extra explain.json] [--mdx explainer.mdx] [--ready ready.json] [--runtime REPO] \
        [--explainer-url URL] [--no-html]

The agent writes the explainer as MDX (the narrative in Markdown, with the data components of
visual-explainer: MergeVerdict, PromiseList, CodeRef and the others). The visual-explainer card
`trust-map` (plugins/visual-explainer/cards/trust-map.md) holds the data contract and the rules.
This script is the glue:

  1. It checks the data: the map is valid and has verdicts, each mechanical check gives its
     recorded result again, and no data input holds pasted code (coderef.pasted).
  2. It resolves the code refs at the head (each claim code ref, and each <CodeRef .../> of the
     MDX) and the patch of each control, reads the diff, and writes DIR/refs.resolved.json.
  3. It runs `artifacture export` with the no-hand-copy guard (the repo and the head). The export
     pre-renders the page, validates the data and runs the trust-map checks.
  4. It runs `artifacture trust-map pr-section` for DIR/pr-section.md.

DIR gets explainer.html, refs.resolved.json and pr-section.md. The MDX imports ./trust-map.json,
./explain.json and ./refs.resolved.json, so when DIR is not the folder of the map, the script
copies the map, explain.json and the MDX into DIR first. The default MDX is explainer.mdx next to
the map. --no-html stops after step 2 and writes pr-section.md.

--runtime is the Artifacture checkout. $UNDERSTANDO_VE_RUNTIME, then ve_runtime in
~/.understando/config.toml, set it too. The default asks the visual-explainer CLI: `node ~/.claude/skills/visual-explainer/scripts/artifacture.mjs path`.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coderef  # noqa: E402
import mechanical  # noqa: E402
import tm  # noqa: E402

REFS_SCHEMA = 1
LANG = {".py": "python", ".ts": "ts", ".tsx": "tsx", ".js": "js", ".mjs": "js", ".json": "json",
        ".md": "markdown", ".sh": "bash", ".toml": "toml", ".yml": "yaml", ".yaml": "yaml"}
# A <CodeRef .../> tag of the MDX: its string attributes and its JSON attributes.
CODEREF = re.compile(r"<CodeRef\b(.*?)/>", re.S)
ATTR = re.compile(r'(\w+)=(?:"([^"]*)"|\{([^{}]*)\})')
REF_KEYS = ("path", "symbol", "part", "match", "context", "start", "end")


def fail(message: str) -> None:
    tm.fail("explain.py: " + message, 1)


def git(repo: str, *args: str) -> str:
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if out.returncode != 0:
        fail(f"git {' '.join(args[:2])} failed: {out.stderr.strip()}")
    return out.stdout


def runtime_path(explicit: str | None) -> str:
    """The Artifacture checkout: --runtime, then $UNDERSTANDO_VE_RUNTIME or ve_runtime of
    ~/.understando/config.toml, then the visual-explainer CLI."""
    import config
    if explicit or config.ve_runtime():
        return explicit or config.ve_runtime()
    cli = Path.home() / ".claude/skills/visual-explainer/scripts/artifacture.mjs"
    out = subprocess.run(["node", str(cli), "path"], capture_output=True, text=True)
    if out.returncode != 0:
        tm.fail("cannot resolve the Artifacture runtime; pass --runtime")
    return out.stdout.strip().splitlines()[-1]


def mdx_refs(text: str) -> list[dict]:
    """The code ref of each <CodeRef .../> tag. An attribute that is not JSON (refs={refs}) is not part of the ref."""
    refs = []
    for tag in CODEREF.finditer(text):
        ref = {}
        for key, string, expr in ATTR.findall(tag.group(1)):
            if key not in REF_KEYS:
                continue
            if string or expr == "":
                ref[key] = string
            else:
                try:
                    ref[key] = json.loads(expr)
                except json.JSONDecodeError:
                    fail(f"the CodeRef attribute {key}={{{expr}}} is not a JSON value")
        if "path" not in ref:
            fail(f"a CodeRef has no path: {tag.group(0)[:120]}")
        refs.append(ref)
    return refs


def resolve_refs(repo: str, data: dict, refs: list[dict]) -> list[dict]:
    """Each ref at the head: the excerpt (capped), the whole span (for the unclaimed level) and the permalink."""
    out, seen = [], set()
    for ref in refs:
        key = coderef.ref_key(ref)
        if key in seen:
            continue
        seen.add(key)
        try:
            r = coderef.resolve(repo, data["head"], ref)
            whole = coderef.resolve(repo, data["head"], ref, cap=False)
        except coderef.AnchorError as exc:
            fail(f"a code ref does not resolve at the head: {exc}. Fix the ref (understando snippet), then build again.")
        out.append({"ref": json.loads(key), "path": ref["path"], "start": r.start, "end": r.end, "span": [whole.start, whole.end],
                    "language": LANG.get(Path(ref["path"]).suffix, "text"), "excerpt": r.excerpt,
                    "permalink": coderef.permalink(repo, data["head"], ref["path"], r.start, r.end, data.get("repo"))})
    return out


def formal_roots(v: dict) -> list[str]:
    """The folders that the edit paths of a formal control can be relative to: the repo root, then
    each folder above the formal artifact (projects/x/formal/lean/, ..., projects/x/)."""
    parts = (v.get("formal") or {}).get("artifact", "").split("/")[:-1]
    return [""] + ["/".join(parts[:i]) + "/" for i in range(len(parts), 0, -1)]


def control_edits(repo: str, data: dict) -> dict[str, list[dict]]:
    """The real before and after of each control: the patch of its scratch worktree (result.diff),
    else the same resolution in memory at the commit where the control runs. A formal control runs
    on the ready branch, with its paths relative to the formal artifact."""
    verifiers = {v["id"]: v for v in data["verifiers"]}
    ready = (data.get("ready") or {}).get("head") or subprocess.run(
        ["git", "-C", repo, "rev-parse", "--verify", "-q", f"refs/heads/understando/{data.get('pr')}-ready"], capture_output=True, text=True).stdout.strip() or None
    out = {}
    for k in data["controls"]:
        v = verifiers[k["verifier"]]
        commits = [c for c in (v.get("at"), ready if "formal" in v else None, data["head"]) if c]
        r = k.get("result") or {}
        patches, error = None, None
        if r.get("diff") and r.get("head") in commits[:1]:
            patches = coderef.split_patch(r["diff"])
        tries = [(c, root) for c in commits for root in (formal_roots(v) if "formal" in v else [""])]
        for commit, root in tries if patches is None else []:
            try:
                patches = coderef.control_patches(repo, commit, [{**e, "path": root + e["path"]} for e in k["edits"]])
                break
            except coderef.AnchorError as exc:
                error = error or exc
        if patches is None and error and "formal" not in v and any(e["op"] in coderef.ANCHOR_OPS for e in k["edits"]):
            fail(f"control {k['id']}: its anchor does not resolve at {commits[0][:10]}: {error}")
        rows = []
        if patches is None:
            # A recorded formal control that resolves nowhere: show its edits as they are.
            for e in k["edits"]:
                lang = LANG.get(Path(e["path"]).suffix, "text")
                if e["op"] == "replace" and e.get("find") != e.get("replace"):
                    rows.append({"path": e["path"], "language": lang, "before": e["find"], "after": e["replace"]})
                elif e["op"] == "append" and e.get("text"):
                    rows.append({"path": e["path"], "language": lang, "before": "", "after": e["text"]})
                else:
                    detail = ", ".join(f"{a} {b}" for a, b in e.items() if a not in ("op", "path"))
                    rows.append({"path": e["path"] + (": " + detail if detail else ""), "language": lang, "note": e["op"]})
        else:
            for path, patch in patches:
                lang = LANG.get(Path(path).suffix, "text")
                rows.append({"path": path, "language": lang, "patch": patch} if patch is not None else {"path": path, "language": lang, "note": "changed bytes"})
        out[k["id"]] = rows
    return out


def diff_data(repo: str, base: str, head: str) -> dict:
    """git diff --numstat, the deleted and created files, and the added line ranges, base to head."""
    files = {}
    for line in git(repo, "diff", "--numstat", "--no-renames", base, head).splitlines():
        a, d, path = line.split("\t", 2)
        if a != "-":
            files[path] = [int(a), int(d)]
    added: dict[str, list[list[int]]] = {}
    current = None
    for line in git(repo, "diff", "-U0", "--no-renames", base, head).splitlines():
        if line.startswith("+++ "):
            current = None if line == "+++ /dev/null" else line[6:]
            if current:
                added.setdefault(current, [])
        elif line.startswith("@@") and current:
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            start, count = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            if count:
                added[current].append([start, start + count - 1])
    names = lambda f: git(repo, "diff", "--name-only", "--no-renames", f"--diff-filter={f}", base, head).split()  # noqa: E731
    return {"files": files, "deleted": names("D"), "created": names("A"), "added": added}


JS_DEF = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\*?|class)\s+([A-Za-z_$][\w$]*)"
                    r"|^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\(|function)")


def changed_symbols(repo: str, head: str, diff: dict) -> tuple[dict, list[dict]]:
    """For each changed code file: its changed symbols, most added lines first, and the ref of the
    main one. A Python file maps each added line to the innermost def or class at the head; another
    file lists the functions and classes on its added lines."""
    out, mains = {}, []
    for path, spans in diff["added"].items():
        if path in diff["deleted"] or not spans or Path(path).suffix not in (".py", ".ts", ".tsx", ".js", ".mjs", ".jsx"):
            continue
        text = coderef.show(repo, head, path)
        if text is None:
            continue
        added = [n for a, b in spans for n in range(a, b + 1)]
        counts: dict[str, int] = {}
        if path.endswith(".py"):
            try:
                syms = [x for x in coderef.python_symbols(text, path) if isinstance(x.node, (coderef.ast.FunctionDef, coderef.ast.AsyncFunctionDef, coderef.ast.ClassDef))]
            except coderef.AnchorError:
                syms = []
            for n in added:
                inner = [x for x in syms if x.start <= n <= x.end]
                if inner:
                    best = min(inner, key=lambda x: x.end - x.start)
                    counts[best.qual] = counts.get(best.qual, 0) + 1
        else:
            rows = text.splitlines()
            for n in added:
                m = JS_DEF.match(rows[n - 1]) if n <= len(rows) else None
                if m:
                    counts[m.group(1) or m.group(2)] = counts.get(m.group(1) or m.group(2), 0) + 1
        names = sorted(counts, key=lambda k: (-counts[k], k))
        main = None
        for name in names[:3]:
            ref = {"path": path, "symbol": name}
            try:
                coderef.resolve(repo, head, ref)
            except coderef.AnchorError:
                continue
            main = ref
            break
        out[path] = {"names": names, "main": main}
        if main:
            mains.append(main)
    return out, mains


def stage(src: Path, dest: Path) -> None:
    if src.resolve() != dest.resolve():
        shutil.copyfile(src, dest)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--extra")
    ap.add_argument("--mdx", help="the explainer MDX; default: explainer.mdx next to the map")
    ap.add_argument("--ready", help="ready.json of the run: the ready checklist of the PR section")
    ap.add_argument("--runtime")
    ap.add_argument("--explainer-url")
    ap.add_argument("--no-html", action="store_true", help="resolve the refs and write pr-section.md; no HTML export")
    ap.add_argument("--journal", help="ignored: the agent writes the why level from the journal (cards/trust-map.md)")
    args = ap.parse_args()
    data = tm.load(args.map)
    errors = tm.validate(data)
    if errors:
        fail("the map is invalid:\n" + "\n".join(errors))
    if "summary" not in data:
        fail("run scripts/verdicts.py first; the map has no verdicts")
    for v in data["verifiers"]:
        if "mechanical" in v:
            got = mechanical.run(args.repo, data["base"], data["head"], v["mechanical"])
            old = v["mechanical"].get("result") or {}
            if (old.get("status"), old.get("detail")) != (got["status"], got["detail"]):
                fail(f"{v['id']}: the mechanical check now gives {got['status']} ({got['detail'].splitlines()[0]}); "
                     f"the map records {old.get('status')}. Run scripts/mechanical.py, then verdicts.py.")
    extra = tm.load(args.extra) if args.extra else {}
    pasted = coderef.pasted(args.repo, data["head"], coderef.guard_inputs(data, extra, []))
    if pasted:
        fail("the input holds code that a person or a model typed. Code comes in through a ref:\n  " + "\n  ".join(pasted))
    mdx = Path(args.mdx) if args.mdx else Path(args.map).parent / "explainer.mdx"
    if not args.no_html and not mdx.is_file():
        fail(f"no explainer MDX at {mdx}. Write it as the visual-explainer card trust-map tells you (cards/trust-map.md).")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stage(Path(args.map), out / "trust-map.json")
    if args.extra:
        stage(Path(args.extra), out / "explain.json")
    elif not (out / "explain.json").exists():
        (out / "explain.json").write_text("{}\n", encoding="utf-8")
    refs = [r for c in data["claims"] for r in c.get("code", [])]
    if mdx.is_file():
        stage(mdx, out / "explainer.mdx")
        refs += mdx_refs(mdx.read_text(encoding="utf-8"))
    diff = diff_data(args.repo, data["base"], data["head"])
    diff["symbols"], mains = changed_symbols(args.repo, data["head"], diff)
    resolved = resolve_refs(args.repo, data, refs)
    # The main changed symbol of a file is a link to read, not an excerpt.
    have = {coderef.ref_key(r["ref"]) for r in resolved}
    resolved += [{**r, "excerpt": "", "link_only": True} for r in resolve_refs(args.repo, data, mains) if coderef.ref_key(r["ref"]) not in have]
    body = {"schema": REFS_SCHEMA, "head": data["head"], "repo": data.get("repo"), "refs": resolved,
            "controls": control_edits(args.repo, data), "diff": diff}
    (out / coderef.CACHE_NAME).write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    runtime = runtime_path(args.runtime)
    if not args.no_html:
        cli = [str(Path(runtime) / "scripts" / "artifacture.mjs"), "export", str(out / "explainer.mdx"), "--out", str(out / "explainer.html"),
               "--guard-repo", str(args.repo), "--guard-head", data["head"]]
        if subprocess.run(["node", *cli]).returncode != 0:
            fail("the export failed. Fix the MDX or the data, not the HTML.")
    section = ["node", str(Path(runtime) / "scripts" / "ve-mdx" / "trust-map.mjs"), "pr-section", "--map", str(out / "trust-map.json"),
               "--refs", str(out / coderef.CACHE_NAME), "--explain", str(out / "explain.json"), "--out", str(out / "pr-section.md")]
    if args.ready and Path(args.ready).is_file():
        section += ["--ready", args.ready]
    if args.explainer_url:
        section += ["--explainer-url", args.explainer_url]
    if subprocess.run(section).returncode != 0:
        fail("the PR section failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
