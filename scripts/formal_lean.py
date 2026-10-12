#!/usr/bin/env python3
"""Build a Lean model, check its axioms, hash its theorems, and run its controls and vectors.

    python3 scripts/formal_lean.py check   --project DIR --import Mod --theorem Ns.thm [--theorem ...]
    python3 scripts/formal_lean.py control --project DIR --file REL.lean --symbol NAME [--match RE]
                                           [--op delete-line|replace-with|...] [--with TEXT]
                                           [--pattern REGEX]
    python3 scripts/formal_lean.py vectors --project DIR --exe NAME --out FILE [--check]
    python3 scripts/formal_lean.py attempt --project DIR --file REL.lean

check    runs `lake build`, then `#print axioms` for each theorem. Green only when the build
         passes, no source file holds `sorry`, `admit` or a new `axiom`, and each theorem depends
         only on propext, Quot.sound and Classical.choice. Prints one JSON record with the sha256 of
         each theorem's source block and of every .lean file. Exit 0 green, 1 red, 2 error.
control  copies the project (with its .lake build cache) to a temp dir, applies one anchor edit
         (the planted wrong model; coderef.py: --symbol is a `theorem|def|lemma` name, --match a
         unique text in it, --op one of its anchor ops, --with the new text), and runs `lake build`.
         The deprecated --find/--replace pair still works and prints a warning. Exit 0 when the build goes
         red (and the output holds --pattern); exit 1 when it stays green: the theorems cannot
         fail on that edit.
vectors  runs `lake exe NAME` and writes its stdout to FILE. With --check, compares instead and
         exits 1 on drift: the committed vectors no longer match the model.
attempt  elaborates one file that is outside the default targets (a proof attempt) and prints
         its result. Exit 0 when it builds, 1 when Lean reports an error.

Standard library only; `lake` must be on PATH (elan).
"""

from __future__ import annotations

import argparse
import hashlib
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
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import coderef  # noqa: E402

ALLOWED = {"propext", "Quot.sound", "Classical.choice"}
TAIL = 40
DECL = re.compile(r"^(?:@\[[^\]]*\]\s*)?(?:private\s+|protected\s+|noncomputable\s+)*"
                  r"(theorem|lemma|def|abbrev|instance|structure|inductive|axiom|example|namespace|end|section|open)\b")



def _rerun_json(obj, **kw) -> str:
    """The JSON result, with the call that made it (formalize --recheck runs it again)."""
    if isinstance(obj, dict):
        obj = {**obj, "rerun": {"script": Path(__file__).name, "args": sys.argv[1:], "cwd": os.getcwd()}}
    return json.dumps(obj, **kw)

def lake(project: Path, *args: str, timeout: int = 1800, stdin: str | None = None) -> tuple[int, str, float]:
    start = time.monotonic()
    out = subprocess.run(["lake", *args], cwd=project, capture_output=True, text=True, timeout=timeout,
                         input=stdin)
    return out.returncode, out.stdout + out.stderr, round(time.monotonic() - start, 2)


def sources(project: Path) -> list[Path]:
    return sorted(p for p in project.rglob("*.lean") if ".lake" not in p.parts)


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def theorem_block(project: Path, full_name: str) -> tuple[Path, int, str] | None:
    """The source block of `theorem <short name>`: from its line to the next top-level decl."""
    short = full_name.split(".")[-1]
    head = re.compile(rf"^(?:@\[[^\]]*\]\s*)?(?:private\s+|protected\s+)*(theorem|lemma)\s+{re.escape(short)}\b")
    for path in sources(project):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if head.match(line):
                end = i + 1
                while end < len(lines) and not DECL.match(lines[end]) and not lines[end].startswith("/--"):
                    end += 1
                return path, i + 1, "\n".join(lines[i:end]).rstrip() + "\n"
    return None


def forbidden(project: Path) -> list[str]:
    hits = []
    for path in sources(project):
        text = re.sub(r"/-.*?-/", "", path.read_text(encoding="utf-8"), flags=re.S)
        for n, line in enumerate(text.splitlines(), 1):
            code = line.split("--", 1)[0]
            if re.search(r"\bsorry\b|\badmit\b", code) or re.match(r"\s*axiom\s", code):
                hits.append(f"{path.relative_to(project)}:{n}: {line.strip()}")
    return hits


def axioms(project: Path, imports: list[str], theorems: list[str]) -> tuple[dict[str, list[str] | None], str]:
    probe = project / "_understando_axioms.lean"
    probe.write_text("".join(f"import {m}\n" for m in imports)
                     + "".join(f"#print axioms {t}\n" for t in theorems), encoding="utf-8")
    try:
        _, out, _ = lake(project, "env", "lean", probe.name)
    finally:
        probe.unlink(missing_ok=True)
    found: dict[str, list[str] | None] = {t: None for t in theorems}
    for t in theorems:
        if m := re.search(rf"'{re.escape(t)}' depends on axioms: \[([^\]]*)\]", out):
            found[t] = [a.strip() for a in m.group(1).split(",") if a.strip()]
        elif re.search(rf"'{re.escape(t)}' does not depend on any axioms", out):
            found[t] = []
    return found, out


def cmd_check(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    code, out, seconds = lake(project, "build")
    record: dict[str, object] = {
        "build": {"exit": code, "seconds": seconds, "output_tail": "\n".join(out.strip().splitlines()[-TAIL:])},
        "files": {str(p.relative_to(project)): sha(p.read_bytes()) for p in sources(project)},
    }
    if code != 0:
        record["status"] = "red"
        record["why"] = "lake build failed"
        print(_rerun_json(record, indent=2))
        return 1
    found, raw = axioms(project, args.imports, args.theorem)
    bad = forbidden(project)
    theorems = {}
    clean = not bad
    for t in args.theorem:
        block = theorem_block(project, t)
        ax = found[t]
        ok = ax is not None and set(ax) <= ALLOWED
        clean = clean and ok
        theorems[t] = {
            "axioms": ax,
            "axioms_clean": ok,
            "file": str(block[0].relative_to(project)) if block else None,
            "line": block[1] if block else None,
            "sha256": sha(block[2].encode()) if block else None,
        }
    record.update({"theorems": theorems, "forbidden": bad, "status": "green" if clean else "red"})
    if not clean:
        record["why"] = "sorry, admit, a new axiom, or an axiom outside the allowed three"
        record["axioms_output"] = raw[-2000:]
    record["tree_sha256"] = sha("".join(f"{k} {v}\n" for k, v in sorted(dict(record["files"]).items())).encode())
    print(_rerun_json(record, indent=2))
    return 0 if clean else 1


def plant(args: argparse.Namespace, text: str) -> tuple[dict, str]:
    """(the edit that was applied, the planted text). An anchor edit, else the deprecated find/replace."""
    if args.find is not None:
        print("formal_lean.py: --find/--replace is deprecated; use --symbol, --match, --op and --with", file=sys.stderr)
        if args.replace is None:
            raise coderef.AnchorError("--find needs --replace")
        edit = {"op": "replace", "path": args.file, "find": args.find, "replace": args.replace}
        return edit, coderef.edit_text(text, edit)
    if not (args.symbol or args.match):
        raise coderef.AnchorError("a control needs --symbol or --match (an anchor edit)")
    edit = coderef.cli_edit(args.file, args.op, args.symbol, args.match, args.with_)
    return edit, coderef.apply_text(text, edit)


def cmd_control(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    tmp = Path(tempfile.mkdtemp(prefix="lean-control-")) / project.name
    try:
        shutil.copytree(project, tmp, symlinks=True)
        target = tmp / args.file
        text = target.read_text(encoding="utf-8")
        try:
            edit, after = plant(args, text)
        except coderef.AnchorError as exc:
            print(_rerun_json({"status": "error", "note": f"ANCHOR ERROR: {exc}"}))
            return 2
        target.write_text(after, encoding="utf-8")
        code, out, seconds = lake(tmp, "build")
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    status = "green" if code == 0 else "red"
    matched = re.search(args.pattern, out) is not None if (status == "red" and args.pattern) else None
    print(_rerun_json({"status": status, "exit": code, "seconds": seconds, "matched": matched,
                      "control": {"file": args.file, "edit": edit},
                      "output_tail": "\n".join(out.strip().splitlines()[-TAIL:])}, indent=2))
    if status == "red" and matched is not False:
        return 0
    return 1 if status == "green" else 2


def cmd_vectors(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    code, out, _ = lake(project, "build", args.exe)
    if code != 0:
        print(out[-2000:], file=sys.stderr)
        return 2
    exe = project / ".lake" / "build" / "bin" / args.exe
    res = subprocess.run([str(exe)], capture_output=True, text=True, check=True)
    path = Path(args.out)
    if args.check:
        same = path.exists() and path.read_text(encoding="utf-8") == res.stdout
        print(_rerun_json({"status": "green" if same else "red", "vectors": str(path),
                          "sha256": sha(res.stdout.encode()), "lines": res.stdout.count("\n")}))
        return 0 if same else 1
    path.write_text(res.stdout, encoding="utf-8")
    print(_rerun_json({"status": "green", "vectors": str(path), "sha256": sha(res.stdout.encode()),
                      "lines": res.stdout.count("\n")}))
    return 0


def cmd_attempt(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    code, out, seconds = lake(project, "env", "lean", args.file)
    print(_rerun_json({"status": "green" if code == 0 else "red", "exit": code, "seconds": seconds,
                      "file": args.file, "output_tail": "\n".join(out.strip().splitlines()[-TAIL:])}, indent=2))
    return 0 if code == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("--project", required=True)
    p.add_argument("--import", dest="imports", action="append", required=True)
    p.add_argument("--theorem", action="append", required=True)
    p = sub.add_parser("control")
    p.add_argument("--project", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--symbol", help="a theorem, lemma or def name")
    p.add_argument("--match", help='a literal, or "/RE/"; it must occur once in the symbol')
    p.add_argument("--op", choices=coderef.ANCHOR_OPS)
    p.add_argument("--with", dest="with_", help="the new text (replace-with)")
    p.add_argument("--find", help="deprecated: use the anchor flags")
    p.add_argument("--replace", help="deprecated: use the anchor flags")
    p.add_argument("--pattern")
    p = sub.add_parser("vectors")
    p.add_argument("--project", required=True)
    p.add_argument("--exe", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--check", action="store_true")
    p = sub.add_parser("attempt")
    p.add_argument("--project", required=True)
    p.add_argument("--file", required=True)
    args = ap.parse_args()
    return {"check": cmd_check, "control": cmd_control, "vectors": cmd_vectors, "attempt": cmd_attempt}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
