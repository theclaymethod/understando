"""understando export: the data and the code references that an explainer needs.

    understando export [--base REF] [--out DIR]

It writes two files for visual-explainer to render (the default DIR is $R/export/):

- verify-data.json: the features, the invariants (with their author), the claims with their derived
  strength and bar, the checks with their state and their last results, the controls with their
  results, the mutation runs (summary, survivors, kill matrix), the last proof of the verify skill
  and the last upkeep pass. Each code ref is a key into refs.resolved.json.
- refs.resolved.json: each code ref resolved at its commit (coderef.ref_commit: the store head, or
  the understando branch for a file that only the branch has), with the excerpt, the line numbers,
  the permalink at that commit and, with a base, the diff line marks (added, modified, removed).
  It also holds the patch of each control: the real before and after of its planted bug.

The export refuses text in the store that is a copy of code at the head (the no-hand-copy guard):
write a code ref instead (`understando snippet`). understando writes no page: visual-explainer
renders these files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import coderef  # noqa: E402
import store  # noqa: E402
import strength  # noqa: E402

LANG = {".py": "python", ".ts": "ts", ".tsx": "tsx", ".js": "js", ".mjs": "js", ".json": "json", ".lean": "lean",
        ".tla": "tla", ".md": "markdown", ".sh": "bash", ".toml": "toml", ".yml": "yaml", ".yaml": "yaml"}


def hunks(repo: Path, base: str, head: str) -> dict[str, list[tuple[int, list[str], int, int]]]:
    """Per file, each hunk of `git diff -U0` base to head: (its first base line, the removed lines,
    its first head line, the number of added lines)."""
    out: dict[str, list] = {}
    current, removed = None, None
    for line in store.git(repo, "diff", "-U0", "--no-renames", base, head).splitlines():
        if line.startswith("diff --git "):
            current, removed = None, None
        elif line.startswith("+++ "):
            current = None if line == "+++ /dev/null" else line[6:]
        elif line.startswith("@@") and current:
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            removed = []
            out.setdefault(current, []).append((int(m.group(1)), removed, int(m.group(2)), int(m.group(3) if m.group(3) is not None else 1)))
        elif removed is not None and line.startswith("-"):
            removed.append(line[1:])
    return out


def line_changes(hs: list, start: int, end: int) -> dict:
    """The diff marks of the head lines start..end: added, modified (one for each removed line at
    the top of a hunk) and the removed base lines, each before the head line `at`."""
    out: dict = {"added": [], "modified": [], "removed": []}
    for base, removed, first, count in hs:
        new = range(first, first + count)
        at = first if count else first + 1
        if not (any(start <= n <= end for n in new) if count else start < at <= end):
            continue
        out["modified"] += [n for n in new[:len(removed)] if start <= n <= end]
        out["added"] += [n for n in new[len(removed):] if start <= n <= end]
        out["removed"] += [{"at": at, "base": base + i, "text": t} for i, t in enumerate(removed)]
    return out


def resolve_refs(repo: Path, data: dict, base: str | None) -> tuple[list[dict], list[str]]:
    rows, misses, seen = [], [], set()
    head = coderef.rev(repo, data["head"])
    diff = hunks(repo, base, head) if base else {}
    for where, ref, at in coderef.walk_refs(data):
        key = coderef.ref_key(ref)
        if key in seen:
            continue
        seen.add(key)
        try:
            r, commit = coderef.resolve_for(repo, data, ref, at)
            whole = coderef.resolve(repo, commit, ref, cap=False)
            sha = coderef.rev(repo, commit)
        except coderef.AnchorError as exc:
            misses.append(f"{where}: {exc}")
            continue
        row = {"key": key, "ref": json.loads(key), "path": ref["path"], "start": r.start, "end": r.end, "span": [whole.start, whole.end],
               "language": LANG.get(Path(ref["path"]).suffix, "text"), "excerpt": r.excerpt, "commit": sha, "cut": r.cut,
               "permalink": coderef.permalink(repo, sha, ref["path"], r.start, r.end, data.get("repo"))}
        if sha != head:
            row.update(on_ready_branch=True, branch=(data.get("ready") or {}).get("branch"))
        elif base:
            row["changes"] = line_changes(diff.get(ref["path"], []), r.start, r.end)
        rows.append(row)
    return rows, misses


def control_patches(repo: Path, data: dict) -> dict[str, list[dict]]:
    """The real before and after of each control: the diff of its scratch worktree, else the same
    resolution in memory at its commit."""
    checks = {v["id"]: v for v in data["checks"]}
    out = {}
    for k in data["controls"]:
        v = checks[k["check"]]
        r = k.get("result") or {}
        rows = []
        if r.get("diff"):
            rows = [{"path": p, "language": LANG.get(Path(p).suffix, "text"), "patch": patch} for p, patch in coderef.split_patch(r["diff"])]
        else:
            commit = v.get("at") or data["head"]
            try:
                rows = [{"path": p, "language": LANG.get(Path(p).suffix, "text"), **({"patch": patch} if patch else {"note": "changed bytes"})}
                        for p, patch in coderef.control_patches(repo, commit, k["edits"])]
            except coderef.AnchorError as exc:
                rows = [{"path": e["path"], "note": f"{e['op']}: {exc}"} for e in k["edits"]]
        out[k["id"]] = rows
    return out


def build(data: dict, rep: dict, refs: list[dict]) -> dict:
    keys = {r["key"] for r in refs}
    refkeys = lambda item: [coderef.ref_key(r) for r in item.get("code", []) if coderef.ref_key(r) in keys]  # noqa: E731
    by_claim = {c["id"]: c for c in rep["claims"]}
    trim = lambda r: {k: r[k] for k in ("status", "exit", "seconds", "score", "ran_at", "head", "note", "evidence", "matched", "output_tail") if r and k in r}  # noqa: E731
    return {
        "schema": "understando.export/1", "repo": data["repo"], "app": data["app"], "head": data["head"], "base": data.get("base"),
        "skill": data.get("skill"), "ready": data.get("ready"),
        "ladder": {str(k): v for k, v in store.LADDER_NAMES.items()},
        "features": [{**f, "claims": [c["id"] for c in data["claims"] if c.get("feature") == f["id"]],
                      "checks": [v["id"] for v in data["checks"] if v.get("feature") == f["id"]]} for f in data["features"]],
        "invariants": [{k: i[k] for k in ("id", "feature", "text", "author", "status", "shape", "risky", "evidence", "possible_bug") if k in i}
                       | {"code": refkeys(i)} for i in data["invariants"]],
        "claims": [{"id": c["id"], "feature": c.get("feature"), "text": c["text"], "invariants": c.get("invariants", []),
                    "checks": c["checks"], "parts": by_claim[c["id"]]["parts"], "strength": by_claim[c["id"]]["verdict"],
                    "tier": by_claim[c["id"]]["tier"], "bar_met": by_claim[c["id"]]["bar_met"], "why": by_claim[c["id"]]["why"],
                    "code": refkeys(c)} for c in data["claims"]],
        "checks": [{"id": v["id"], "feature": v.get("feature"), "name": v.get("name"), "kind": v["kind"], "rung": store.ladder(v),
                    "state": v.get("state"), "command": (v.get("command") or {}).get("argv"), "at": v.get("at"),
                    "baseline": trim(v.get("baseline")), "red_first": trim(v.get("red_first")),
                    "formal": v.get("formal"), "property": v.get("property"),
                    "formal_verdict": ((v.get("formal_record") or {}).get("formal") or {}).get("verdict"),
                    "code": refkeys(v)} for v in data["checks"]],
        "controls": [{"id": k["id"], "check": k["check"], "kind": k["kind"], "description": k.get("description"),
                      "outcome": strength.outcome(next(v for v in data["checks"] if v["id"] == k["check"]), k),
                      "result": trim(k.get("result")), "patch": k["id"]} for k in data["controls"]],
        "mutation": [{"id": m["id"], "tool": m["tool"], "feature": m.get("feature"), "paths": m["paths"], "at": m.get("at"),
                      "summary": m["summary"], "lines": m.get("lines"),
                      "mutants": [{x: mu[x] for x in ("id", "path", "line", "status", "filter", "diff", "killed_by", "operator") if x in mu} for mu in m["mutants"]],
                      "matrix": m.get("matrix", {})} for m in data["mutation"]],
        "flags": rep["flags"], "summary": rep["summary"], "proved": data.get("proved"), "maintained": data.get("maintained"),
    }


def main(c: store.Ctx, argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="understando export", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="the commit before the work: the diff marks of each code ref")
    ap.add_argument("--out", help="the folder for the two files (default: $R/export)")
    args = ap.parse_args(argv)
    repo = c.need_repo()
    data = c.need_data()
    base = coderef.rev(repo, args.base) if args.base else data.get("base")
    if args.base:
        data["base"] = base
    pasted = coderef.pasted(repo, data["head"], coderef.guard_inputs(data))
    if pasted:
        store.fail("export: refuse: the store holds pasted code:\n" + "\n".join(pasted), 1)
    rep = strength.apply(data)
    refs, misses = resolve_refs(repo, data, base)
    if misses:
        store.fail("export: these code refs do not resolve; fix each ref (understando snippet), then export again:\n" + "\n".join(misses), 1)
    out = Path(args.out).resolve() if args.out else c.run / "export"
    refusal = store.refuse_run_write(out)
    if refusal:
        store.fail(refusal, 1)
    out.mkdir(parents=True, exist_ok=True)
    (out / "refs.resolved.json").write_text(json.dumps({"schema": 2, "head": coderef.rev(repo, data["head"]), "refs": refs,
                                                         "controls": control_patches(repo, data)}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "verify-data.json").write_text(json.dumps(build(data, rep, refs), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    c.save(data)
    store.emit(c, {"out": str(out), "refs": len(refs), "claims": len(data["claims"]), "summary": rep["summary"]},
               f"export: {out / 'verify-data.json'} and {out / 'refs.resolved.json'} ({len(refs)} code refs, "
               + ", ".join(f"{k} {v}" for k, v in rep["summary"].items()) + "). visual-explainer renders them.")
    return 0
