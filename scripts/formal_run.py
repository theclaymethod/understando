#!/usr/bin/env python3
"""Run one conformance command, at the head or on a planted defect, and print one JSON result.

    python3 scripts/formal_run.py --cwd DIR [--env K=V]... -- ARGV...
    python3 scripts/formal_run.py --cwd DIR --copy ROOT [--link REL]... --edit EDIT.json [--edit ...]
                                  [--pattern REGEX] --expect red -- ARGV...

Without --copy the command runs in DIR as it is. With --copy, ROOT (an ancestor of DIR, or DIR
itself) is copied to a temp dir without .git, .venv, .lake, node_modules and caches; each --link
REL becomes a symlink to ROOT/REL (for example a .venv, so the copy needs no install); each edit is
applied (the run_control.py edit format, with the anchors of coderef.py: {"op": "delete-line" |
"invert-condition" | "replace-with" | "drop-allowlist-row" | "corrupt-byte", "path", "symbol",
"match", "with"}; the anchor must resolve to one place in the copy, else the run is an error);
and the command runs in the copy's DIR. The copy is removed afterwards. The typed
{"op": "replace", "path", "find", "replace", "count"} edit still works but is deprecated: it
prints a warning.

The status is green (exit 0), red (exit 1, and --pattern, when given, holds in the output), or
error. With --expect, the script exits 0 only when the status is the expected one: a planted
defect must make the conformance test go red, or it proves nothing.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import coderef  # noqa: E402
from formal_common import rerun_json, scratch  # noqa: E402
from run_control import apply_edit, classify, run_command, tail  # noqa: E402

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
    edits = [json.loads(Path(e).read_text()) if Path(e).is_file() else json.loads(e) for e in args.edit]
    command = {"argv": args.argv, "env": dict(e.split("=", 1) for e in args.env), "timeout_s": args.timeout}
    if args.copy:
        root = Path(args.copy).resolve()
        if not cwd.is_relative_to(root):
            raise SystemExit("--cwd must be inside --copy")
        with scratch("formal-run-") as tmp:
            copy = tmp / root.name
            shutil.copytree(root, copy, ignore=SKIP, symlinks=True)
            for rel in args.link:
                (copy / rel).symlink_to(root / rel)
            for edit in edits:
                if edit.get("op") == "replace":
                    print("formal_run.py: a find/replace edit is deprecated; use an anchor edit (symbol, match, op, with)",
                          file=sys.stderr)
                try:
                    apply_edit(copy, edit)
                except (coderef.AnchorError, ValueError, KeyError, OSError) as exc:
                    print(rerun_json({"status": "error", "note": f"ANCHOR ERROR: {exc}", "edit": edit}, indent=2))
                    return 2
            code, text, seconds = run_command(copy / cwd.relative_to(root), command)
            text = text.replace(str(tmp), "<copy>")
    else:
        code, text, seconds = run_command(cwd, command)
    status = classify(code, command)
    matched = re.search(args.pattern, text, re.M) is not None if (status == "red" and args.pattern) else None
    if matched is False:
        status = "error"  # red for another reason
    result = {"status": status, "exit": code, "seconds": seconds, "matched": matched, "argv": args.argv, "edits": edits,
              "output_tail": tail(text)}
    print(rerun_json(result, indent=2))
    if args.expect:
        return 0 if status == args.expect else 1
    return {"green": 0, "red": 1}.get(status, 2)


if __name__ == "__main__":
    sys.exit(main())
