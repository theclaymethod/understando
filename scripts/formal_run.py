#!/usr/bin/env python3
"""Run one conformance command, at the head or on a planted defect, and print one JSON result.

    python3 scripts/formal_run.py --cwd DIR [--env K=V]... -- ARGV...
    python3 scripts/formal_run.py --cwd DIR --copy ROOT [--link REL]... --edit EDIT.json [--edit ...]
                                  [--pattern REGEX] --expect red -- ARGV...

Without --copy the command runs in DIR as it is. With --copy, ROOT (an ancestor of DIR, or DIR
itself) is copied to a temp dir without .git, .venv, .lake, node_modules and caches; each --link
REL becomes a symlink to ROOT/REL (for example a .venv, so the copy needs no install); each edit is
applied exactly (the run_control.py edit format: {"op": "replace", "path", "find", "replace",
"count"}); and the command runs in the copy's DIR. The copy is removed afterwards.

The status is green (exit 0), red (exit 1, and --pattern, when given, holds in the output), or
error. With --expect, the script exits 0 only when the status is the expected one: a planted
defect must make the conformance test go red, or it proves nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_control import apply_edit  # noqa: E402

TAIL = 40
SKIP = shutil.ignore_patterns(".git", ".venv", ".lake", "node_modules", "__pycache__", ".pytest_cache",
                              ".ruff_cache", "*.pyc")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cwd", required=True)
    ap.add_argument("--copy")
    ap.add_argument("--link", action="append", default=[])
    ap.add_argument("--edit", action="append", default=[])
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--pattern")
    ap.add_argument("--expect", choices=["green", "red"])
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("argv", nargs="+")
    args = ap.parse_args()

    cwd = Path(args.cwd).resolve()
    tmp: Path | None = None
    edits = [json.loads(Path(e).read_text()) if Path(e).is_file() else json.loads(e) for e in args.edit]
    try:
        if args.copy:
            root = Path(args.copy).resolve()
            if not cwd.is_relative_to(root):
                raise SystemExit("--cwd must be inside --copy")
            tmp = Path(tempfile.mkdtemp(prefix="formal-run-"))
            copy = tmp / root.name
            shutil.copytree(root, copy, ignore=SKIP, symlinks=True)
            for rel in args.link:
                (copy / rel).symlink_to(root / rel)
            for edit in edits:
                apply_edit(copy, edit)
            run_dir = copy / cwd.relative_to(root)
        else:
            run_dir = cwd
        env = {**os.environ, **dict(e.split("=", 1) for e in args.env)}
        start = time.monotonic()
        out = subprocess.run(args.argv, cwd=run_dir, capture_output=True, text=True, env=env,
                             timeout=args.timeout, stdin=subprocess.DEVNULL)
        seconds = round(time.monotonic() - start, 2)
        text = out.stdout + out.stderr
        if tmp is not None:
            text = text.replace(str(tmp), "<copy>")
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
    status = {0: "green", 1: "red"}.get(out.returncode, "error")
    matched = re.search(args.pattern, text, re.M) is not None if (status == "red" and args.pattern) else None
    if matched is False:
        status = "error"  # red for another reason
    result = {
        "status": status, "exit": out.returncode, "seconds": seconds, "matched": matched,
        "argv": args.argv, "edits": edits,
        "output_tail": "\n".join(text.rstrip().replace(str(Path.home()), "~").splitlines()[-TAIL:]),
    }
    print(json.dumps(result, indent=2))
    if args.expect:
        return 0 if status == args.expect else 1
    return {"green": 0, "red": 1}.get(status, 2)


if __name__ == "__main__":
    sys.exit(main())
