#!/usr/bin/env python3
"""Run the cheap mechanical checks in a trust map: a grep or a line count, at the PR head.

    python3 scripts/mechanical.py --map trust-map.json --repo <git repo>          # run, record
    python3 scripts/mechanical.py --map trust-map.json --repo <git repo> --check  # exit 1 on drift

A verifier with a `mechanical` block holds one check. Each check reads Git objects only
(`git grep` at the head, `git diff --numstat` from the base to the head), so it needs no
worktree, runs no project code and costs nothing.

  grep-absent   pass when `git grep -E <pattern>` finds no match in <paths> at the head
  grep-present  pass when it finds at least one match
  net-lines     pass when the added minus the removed lines in <paths> equal <expect>

The script writes `mechanical.result` (status pass or fail, the detail and the command) on each
verifier. verdicts.py then rates the verifier `checked` (pass) or `failing` (fail). A claim with
a passing check is Backed, never Asserted. explain.py runs each check again and stops when a
result differs from the recorded one.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tm  # noqa: E402


def git(repo: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def run(repo: str, base: str, head: str, check: dict) -> dict:
    """The result of one mechanical check: {status, detail, command}."""
    op, paths = check["op"], check["paths"]
    import config
    excludes = config.pathspec_excludes(config.for_repo(repo))
    if op in ("grep-absent", "grep-present"):
        argv = ["grep", "-n", "-E", check["pattern"], head, "--", *paths, *excludes]
        out = git(repo, *argv)
        if out.returncode not in (0, 1):
            tm.fail(f"git grep failed: {out.stderr.strip()}", 1)
        hits = [line.split(":", 1)[1] if line.startswith(head) else line for line in out.stdout.splitlines()]
        files = git(repo, "ls-tree", "-r", "--name-only", head, "--", *paths).stdout.split()
        where = ", ".join(paths)
        if hits:
            shown = "\n".join(hits[:10]) + (f"\n... and {len(hits) - 10} more" if len(hits) > 10 else "")
            detail = f"{len(hits)} matches in {where} at {head[:10]}:\n{shown}"
        else:
            detail = f"No match in {len(files)} files under {where} at {head[:10]}."
        ok = not hits if op == "grep-absent" else bool(hits)
        command = "git " + " ".join(shlex.quote(a) for a in argv)
    elif op == "net-lines":
        argv = ["diff", "--numstat", "--no-renames", base, head, "--", *paths]
        out = git(repo, *argv)
        if out.returncode != 0:
            tm.fail(f"git diff failed: {out.stderr.strip()}", 1)
        added = removed = files = 0
        for line in out.stdout.splitlines():
            a, d, _ = line.split("\t", 2)
            if a != "-":
                added, removed, files = added + int(a), removed + int(d), files + 1
        net = added - removed
        ok = net == check["expect"]
        detail = (f"+{added:,} and -{removed:,} lines in {files} files under {', '.join(paths)}: "
                  f"net {net:+,}. The claim says {check['expect']:+,}.")
        command = "git " + " ".join(shlex.quote(a) for a in argv)
    else:
        tm.fail(f"unknown mechanical op {op!r}", 2)
    return {"status": "pass" if ok else "fail", "detail": detail, "command": command, "head": head}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--check", action="store_true", help="exit 1 when a result differs from the recorded one")
    args = ap.parse_args()
    data = tm.load(args.map)
    drift = []
    for v in data["verifiers"]:
        if "mechanical" not in v:
            continue
        got = run(args.repo, data["base"], data["head"], v["mechanical"])
        old = v["mechanical"].get("result") or {}
        if args.check:
            if (old.get("status"), old.get("detail")) != (got["status"], got["detail"]):
                drift.append(v["id"])
        else:
            v["mechanical"]["result"] = {**got, "ran_at": tm.now()}
        print(f"{v['id']:<5} {got['status']:<5} {got['detail'].splitlines()[0]}")
    if args.check:
        if drift:
            print("mechanical results differ: " + ", ".join(drift))
            return 1
        return 0
    tm.save(data, args.map)
    return 0


if __name__ == "__main__":
    sys.exit(main())
