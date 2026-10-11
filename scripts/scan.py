#!/usr/bin/env python3
"""Scan a PR for the map step: changed files, @cc contracts, and changed code that no test names.

    python3 scripts/scan.py --repo R --base B --head H [--src-prefix src/] [--test-prefix tests/]
    python3 scripts/scan.py ... --add MAP     # add contract claims and Gap candidates to MAP

Read-only on the repo: it uses `git diff` and `git show`, never a checkout.

The report lists:
  contracts   each `@cc` directive in a changed file at the head (ID, path, line, first prose line)
  untested    each changed source file under --src-prefix whose stem no test file under
              --test-prefix names at the head. These are Gap candidates.

With --add, the script adds one claim per contract that no claim holds yet (stated: true, because
the author wrote the contract), and one claim per untested file that no claim's code points at
(stated: false). The verdict step then rates each one.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tm  # noqa: E402

CC = re.compile(r"@cc\s+(?:\[[^\]]*\]\s+)?(?P<id>[^\s,:\[\]]+)")
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".go", ".rs", ".java", ".kt", ".swift", ".rb"}
COMMENT_LEAD = re.compile(r'^\s*(?:\*|//+|#+|"""|\'\'\')?\s?')


def git(repo: str, *args: str) -> str:
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if out.returncode != 0:
        tm.fail(f"git {' '.join(args)}: {out.stderr.strip()}")
    return out.stdout


def changed(repo: str, base: str, head: str) -> list[tuple[str, str]]:
    rows = []
    for line in git(repo, "diff", "--name-status", "--no-renames", f"{base}...{head}").splitlines():
        status, path = line.split("\t", 1)
        rows.append((status[0], path))
    return rows


def contracts(repo: str, head: str, paths: list[str]) -> list[dict]:
    found = []
    for path in paths:
        if Path(path).suffix not in SOURCE_SUFFIXES and Path(path).name != "CONTRACTS":
            continue
        lines = git(repo, "show", f"{head}:{path}").splitlines()
        for i, line in enumerate(lines):
            m = CC.search(line)
            if not m:
                continue
            prose = ""
            for nxt in lines[i + 1:i + 4]:
                prose = COMMENT_LEAD.sub("", nxt).strip()
                if prose:
                    break
            found.append({"cc_id": m.group("id"), "path": path, "line": i + 1, "prose": prose})
    return found


def untested(repo: str, head: str, rows: list[tuple[str, str]], src: str, tests: str) -> list[str]:
    test_files = [p for p in git(repo, "ls-tree", "-r", "--name-only", head, tests).splitlines()
                  if Path(p).suffix in SOURCE_SUFFIXES]
    corpus = "\n".join(git(repo, "show", f"{head}:{p}") for p in test_files)
    out = []
    for status, path in rows:
        p = Path(path)
        if status == "D" or not path.startswith(src) or p.suffix not in SOURCE_SUFFIXES:
            continue
        if p.stem.startswith("__"):
            continue
        if not re.search(rf"\b{re.escape(p.stem)}\b", corpus):
            out.append(path)
    return out


def next_id(data: dict) -> str:
    n = 1
    ids = {c["id"] for c in data["claims"]}
    while f"C{n:02d}" in ids:
        n += 1
    return f"C{n:02d}"


def add(data: dict, found: list[dict], gaps: list[str]) -> int:
    added = 0
    have_cc = {c.get("cc_id") for c in data["claims"]}
    for item in found:
        if item["cc_id"] in have_cc:
            continue
        data["claims"].append({
            "id": next_id(data), "cc_id": item["cc_id"], "stated": True,
            "text": item["prose"] or f"The contract {item['cc_id']} holds.",
            "source": f"@cc contract in {item['path']}:{item['line']}",
            "code": [{"path": item["path"], "start": item["line"], "end": item["line"] + 2}],
        })
        have_cc.add(item["cc_id"])
        added += 1
    pointed = {ref["path"] for c in data["claims"] for ref in c.get("code", [])}
    for path in gaps:
        if path in pointed:
            continue
        data["claims"].append({
            "id": next_id(data), "cc_id": None, "stated": False, "layer": "Unstated changes",
            "text": f"The change to {Path(path).name} keeps the intended behavior.",
            "source": f"scan: {path} changed, and no test names it",
            "code": [{"path": path}],
        })
        added += 1
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--src-prefix", default="src/")
    ap.add_argument("--test-prefix", default="tests/")
    ap.add_argument("--add", metavar="MAP")
    args = ap.parse_args()

    rows = changed(args.repo, args.base, args.head)
    live = [p for s, p in rows if s != "D"]
    found = contracts(args.repo, args.head, live)
    gaps = untested(args.repo, args.head, rows, args.src_prefix, args.test_prefix)
    report = {"changed": len(rows), "added": sum(s == "A" for s, _ in rows),
              "deleted": sum(s == "D" for s, _ in rows), "contracts": found, "untested": gaps}
    if args.add:
        data = tm.load(args.add)
        report["claims_added"] = add(data, found, gaps)
        errors = tm.validate(data, promises=False)
        if errors:
            tm.fail("invalid trust map after scan:\n" + "\n".join(errors), 1)
        tm.save(data, args.add)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
