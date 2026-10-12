"""The parts that the formal helpers share: formal_lean.py, formal_tlc.py and formal_run.py.

- rerun_json: the JSON result with the call that made it (formalize --recheck runs it again);
- plant: the anchor edit of a model control, or the deprecated find/replace;
- control_match and control_exit: the pattern check and the exit code of a control;
- vectors_out: compare the vectors with the committed file (--check), or write them;
- sha and scratch: a sha256 text, and a temp folder that goes away at the end.

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # also under python3 -I, which drops the script folder
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import coderef  # noqa: E402


def script() -> str:
    """The file name of the helper that runs: formal_lean.py, formal_tlc.py or formal_run.py."""
    return Path(sys.argv[0]).name


def rerun_json(obj, **kw) -> str:
    """The JSON result, with the call that made it (formalize --recheck runs it again)."""
    if isinstance(obj, dict):
        obj = {**obj, "rerun": {"script": script(), "args": sys.argv[1:], "cwd": os.getcwd()}}
    return json.dumps(obj, **kw)


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


@contextmanager
def scratch(prefix: str):
    """A temp folder, removed at the end, also on failure."""
    with tempfile.TemporaryDirectory(prefix=prefix, ignore_cleanup_errors=True) as tmp:
        yield Path(tmp)


def plant(args: argparse.Namespace, path: str, text: str) -> tuple[dict, str]:
    """(the edit that was applied, the planted text). An anchor edit, else the deprecated find/replace."""
    if args.find is not None:
        print(f"{script()}: --find/--replace is deprecated; use --symbol, --match, --op and --with", file=sys.stderr)
        if args.replace is None:
            raise coderef.AnchorError("--find needs --replace")
        edit = {"op": "replace", "path": path, "find": args.find, "replace": args.replace}
        return edit, coderef.edit_text(text, edit)
    if not (args.symbol or args.match):
        raise coderef.AnchorError("a control needs --symbol or --match (an anchor edit)")
    edit = coderef.cli_edit(path, args.op, args.symbol, args.match, args.with_)
    return edit, coderef.apply_text(text, edit)


def control_match(status: str, pattern: str | None, text: str) -> bool | None:
    """Whether a red control shows its expected pattern; None when it is not red or has no pattern."""
    return re.search(pattern, text) is not None if (status == "red" and pattern) else None


def control_exit(status: str, matched: bool | None) -> int:
    """0 when the control went red (with its pattern), 1 when it stayed green: it cannot fail there, else 2."""
    if status == "red" and matched is not False:
        return 0
    return 1 if status == "green" else 2


def vectors_out(path: Path, text: str, check: bool, checked: dict, written: dict) -> int:
    """With check, compare `text` with the committed file: exit 1 on drift. Else write it."""
    if check:
        same = path.exists() and path.read_text(encoding="utf-8") == text
        print(rerun_json({"status": "green" if same else "red", **checked}))
        return 0 if same else 1
    path.write_text(text, encoding="utf-8")
    print(rerun_json({"status": "green", **written}))
    return 0
