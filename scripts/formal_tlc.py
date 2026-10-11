#!/usr/bin/env python3
"""Run TLC on a TLA+ spec, read its result, and turn its states into test vectors.

    python3 scripts/formal_tlc.py check  --spec DIR/Name.tla [--cfg DIR/Name.cfg] [--no-deadlock-check]
    python3 scripts/formal_tlc.py dump   --spec DIR/Name.tla --cfg DIR/Vectors.cfg --out states.json
    python3 scripts/formal_tlc.py vectors --spec DIR/Name.tla --cfg DIR/Vectors.cfg --done 'result!="running"'
                                          --out vectors.json [--check]
    python3 scripts/formal_tlc.py control --spec DIR/Name.tla [--cfg ...] --symbol Name [--match RE]
                                          [--op delete-line|replace-with|...] [--with TEXT]
                                          [--pattern REGEX]

check    runs TLC once and prints one JSON object: status green (no error), red (an invariant, a
         property or a deadlock failed, with the parsed trace) or error (TLC did not finish). The
         exit is 0 for green, 1 for red, 2 for error.
dump     runs TLC with -dump and writes every distinct state as JSON. A spec that keeps a history
         variable makes each terminal state one whole behaviour: that is the vector source.
vectors  runs dump and keeps the terminal states (those that match --done, `var=json` or
         `var!=json`, repeatable) as test vectors, with the spec and cfg hashes and the cfg's
         constants, one vector per line (--keep VAR keeps only those variables). With --check, it
         compares with the committed file and exits 1 on drift.
control  copies the spec directory to a temp dir, applies one anchor edit to the .tla file (the
         planted wrong spec; coderef.py: --symbol is a `<Name> ==` definition, --match a unique text
         in it, --op one of its anchor ops, --with the new text; the deprecated --find/--replace
         pair still works and prints a warning), runs check, and exits 0 only when TLC goes red (and the red
         output holds --pattern). A control that stays green exits 1: the spec cannot fail there.

Deadlock checking is on by default. Give a spec with terminal states an explicit stutter step
(`Done == phase = "done" /\\ UNCHANGED vars`) rather than turn the check off.

Environment: UNDERSTANDO_JAVA (default $JAVA_HOME/bin/java, then /opt/homebrew/opt/openjdk/bin/java, else java on PATH) and
UNDERSTANDO_TLA2TOOLS (default ~/.understando/tools/tla2tools.jar). Standard library only.
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

TAIL = 40


def java() -> str:
    """The java that ctx.java_bin() finds ($UNDERSTANDO_JAVA, $JAVA_HOME, Homebrew's openjdk, PATH)."""
    import ctx
    return ctx.java_bin() or os.environ.get("UNDERSTANDO_JAVA") or "java"


def jar() -> str:
    import ctx
    return ctx.tla2tools_jar() or os.environ.get("UNDERSTANDO_TLA2TOOLS") or str(Path.home() / ".understando/tools/tla2tools.jar")


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


# ---- TLA+ value parser (the subset TLC prints for states) -------------------------------------

_TOKEN = re.compile(r'\s*(<<|>>|\|->|:>|@@|"(?:[^"\\]|\\.)*"|-?\d+|[A-Za-z_][A-Za-z0-9_]*|[\[\]{}(),])')


def _tokens(text: str) -> list[str]:
    out, pos = [], 0
    text = text.rstrip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise ValueError(f"cannot parse TLA+ value at {text[pos:pos + 30]!r}")
        out.append(m.group(1))
        pos = m.end()
    return out


def parse_value(text: str) -> object:
    """A TLC value as JSON: sequences and tuples are lists, sets are sorted lists, records and
    functions are dicts (keys as strings), strings, ints and booleans as themselves."""
    toks = _tokens(text)
    val, i = _parse(toks, 0)
    if i != len(toks):
        raise ValueError(f"trailing tokens in {text!r}")
    return val


def _parse(t: list[str], i: int) -> tuple[object, int]:
    tok = t[i]
    if tok == "<<":
        return _items(t, i + 1, ">>")
    if tok == "{":
        items, j = _items(t, i + 1, "}")
        return sorted(items, key=lambda x: json.dumps(x, sort_keys=True)), j
    if tok == "[":
        rec: dict[str, object] = {}
        j = i + 1
        while t[j] != "]":
            key = t[j]
            if t[j + 1] != "|->":
                raise ValueError("expected |-> in record")
            val, j = _parse(t, j + 2)
            rec[key] = val
            if t[j] == ",":
                j += 1
        return rec, j + 1
    if tok == "(":
        # A function: (k1 :> v1 @@ k2 :> v2)
        fn: dict[str, object] = {}
        j = i + 1
        while t[j] != ")":
            k, j = _parse(t, j)
            if t[j] != ":>":
                raise ValueError("expected :> in function")
            v, j = _parse(t, j + 1)
            fn[k if isinstance(k, str) else json.dumps(k)] = v
            if t[j] == "@@":
                j += 1
        return fn, j + 1
    if tok.startswith('"'):
        return json.loads(tok), i + 1
    if tok in ("TRUE", "FALSE"):
        return tok == "TRUE", i + 1
    if re.fullmatch(r"-?\d+", tok):
        return int(tok), i + 1
    return tok, i + 1  # a model value


def _items(t: list[str], i: int, close: str) -> tuple[list[object], int]:
    items: list[object] = []
    while t[i] != close:
        v, i = _parse(t, i)
        items.append(v)
        if t[i] == ",":
            i += 1
    return items, i + 1


def parse_state(block: str) -> dict[str, object]:
    """One state as TLC prints it: lines of `/\\ var = value`, a value may span lines."""
    state: dict[str, object] = {}
    for part in re.split(r"(?m)^/\\ ", block.strip()):
        part = part.strip()
        if not part:
            continue
        name, _, value = part.partition(" = ")
        state[name.strip()] = parse_value(" ".join(value.split()))
    return state


# ---- running TLC -------------------------------------------------------------------------------

def run(spec: Path, cfg: Path | None, deadlock_check: bool, dump: Path | None = None,
        timeout: int = 900) -> dict[str, object]:
    spec = spec.resolve()
    meta = Path(tempfile.mkdtemp(prefix="tlc-meta-"))
    argv = [java(), "-XX:+UseParallelGC", "-cp", jar(), "tlc2.TLC", "-workers", "auto",
            "-metadir", str(meta), "-cleanup"]
    if cfg is not None:
        argv += ["-config", str(cfg.resolve())]
    if not deadlock_check:
        argv.append("-deadlock")
    if dump is not None:
        argv += ["-dump", str(dump)]
    argv.append(spec.name)
    start = time.monotonic()
    try:
        out = subprocess.run(argv, cwd=spec.parent, capture_output=True, text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL)
        code, text = out.returncode, out.stdout + out.stderr
    except subprocess.TimeoutExpired:
        code, text = None, "[formal_tlc] timeout"
    finally:
        shutil.rmtree(meta, ignore_errors=True)
    result = read_output(text)
    result.update({
        "exit": code,
        "seconds": round(time.monotonic() - start, 2),
        "spec": spec.name,
        "spec_sha256": sha256(spec),
        "cfg": cfg.name if cfg else None,
        "cfg_sha256": sha256(cfg) if cfg else None,
        "deadlock_checked": deadlock_check,
        "output_tail": "\n".join(text.rstrip().splitlines()[-TAIL:]),
    })
    return result


def read_output(text: str) -> dict[str, object]:
    found = re.search(r"(\d+) states generated, (\d+) distinct states found", text)
    stats = {"generated": int(found.group(1)), "distinct": int(found.group(2))} if found else {}
    if "Model checking completed. No error has been found." in text:
        return {"status": "green", "violation": None, "trace": [], **stats}
    kind, name = None, None
    if m := re.search(r"Error: Invariant (\S+) is violated", text):
        kind, name = "invariant", m.group(1)
    elif m := re.search(r"Error: Action property (\S+) is violated", text):
        kind, name = "action-property", m.group(1)
    elif "Error: Temporal properties were violated" in text:
        kind = "property"
    elif "Error: Deadlock reached" in text:
        kind = "deadlock"
    elif "Error: The behavior up to this point is" in text or "Error: Assumption" in text:
        kind = "error"
    if kind in (None, "error"):
        return {"status": "error", "violation": None, "trace": [], **stats}
    return {"status": "red", "violation": {"kind": kind, "name": name}, "trace": trace(text), **stats}


def trace(text: str) -> list[dict[str, object]]:
    """The error trace: each `State n: <action>` block, parsed."""
    blocks = re.split(r"(?m)^State (\d+): ?(.*)$", text)
    steps: list[dict[str, object]] = []
    for k in range(1, len(blocks) - 2, 3):
        body = blocks[k + 2]
        body = re.split(r"(?m)^(?:\d+ states generated|The number of states|Back to state|"
                        r"Progress|Finished|Error:|\s*$\n\s*$)", body)[0]
        try:
            state = parse_state(body)
        except (ValueError, IndexError):
            state = {"_raw": body.strip()}
        steps.append({"n": int(blocks[k]), "action": blocks[k + 1].strip(), "state": state})
    return steps


def read_dump(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8")
    states = []
    for block in re.split(r"(?m)^State \d+:\s*$", text)[1:]:
        states.append(parse_state(block))
    return states


# ---- commands ----------------------------------------------------------------------------------

def cmd_check(args: argparse.Namespace) -> int:
    res = run(Path(args.spec), Path(args.cfg) if args.cfg else None, not args.no_deadlock_check)
    print(json.dumps(res, indent=2))
    return {"green": 0, "red": 1}.get(str(res["status"]), 2)


def cmd_dump(args: argparse.Namespace) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="tlc-dump-"))
    try:
        res = run(Path(args.spec), Path(args.cfg), not args.no_deadlock_check, dump=tmp / "states")
        if res["status"] != "green":
            print(json.dumps(res, indent=2))
            return 2
        states = read_dump(tmp / "states.dump")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    Path(args.out).write_text(json.dumps(states, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "green", "states": len(states), "out": args.out,
                      "spec_sha256": res["spec_sha256"], "cfg_sha256": res["cfg_sha256"]}))
    return 0


def constants(cfg: Path) -> dict[str, object]:
    """The `CONSTANT name = value` assignments of a cfg file, values parsed."""
    out: dict[str, object] = {}
    section = False
    for line in cfg.read_text(encoding="utf-8").splitlines():
        line = line.split("\\*", 1)[0].strip()
        m = re.match(r"^(CONSTANTS?)\b\s*(.*)$", line)
        if m:
            section, line = True, m.group(2)
        elif re.match(r"^[A-Z_]+\b", line) and "=" not in line:
            section = False
        if section and (a := re.match(r"^(\w+)\s*=\s*(.+)$", line)):
            try:
                out[a.group(1)] = parse_value(a.group(2))
            except ValueError:
                out[a.group(1)] = a.group(2)
    return out


def _matches(state: dict[str, object], conds: list[str]) -> bool:
    for cond in conds:
        neg = "!=" in cond
        var, _, raw = cond.partition("!=" if neg else "=")
        if (state.get(var.strip()) == json.loads(raw)) == neg:
            return False
    return True


def cmd_vectors(args: argparse.Namespace) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="tlc-vectors-"))
    try:
        res = run(Path(args.spec), Path(args.cfg), not args.no_deadlock_check, dump=tmp / "states")
        if res["status"] != "green":
            print(json.dumps(res, indent=2))
            return 2
        states = read_dump(tmp / "states.dump")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    done = sorted((s for s in states if _matches(s, args.done)), key=lambda s: json.dumps(s, sort_keys=True))
    if args.keep:
        done = [{k: v[k] for k in args.keep if k in v} for v in done]
    head = {"spec": res["spec"], "spec_sha256": res["spec_sha256"], "cfg": res["cfg"],
            "cfg_sha256": res["cfg_sha256"], "constants": constants(Path(args.cfg)), "done": args.done,
            "states": len(states)}
    # One vector per line, so the file diffs and greps line by line.
    text = (json.dumps(head, sort_keys=True)[:-1] + ', "vectors": [\n'
            + ",\n".join(json.dumps(v, sort_keys=True, separators=(",", ":")) for v in done) + "\n]}\n")
    out = Path(args.out)
    if args.check:
        same = out.exists() and out.read_text(encoding="utf-8") == text
        print(json.dumps({"status": "green" if same else "red", "vectors": len(done), "out": args.out}))
        return 0 if same else 1
    out.write_text(text, encoding="utf-8")
    print(json.dumps({"status": "green", "states": len(states), "vectors": len(done), "out": args.out,
                      "spec_sha256": res["spec_sha256"]}))
    return 0


def plant(args: argparse.Namespace, name: str, text: str) -> tuple[dict, str]:
    """(the edit that was applied, the planted text). An anchor edit, else the deprecated find/replace."""
    if args.find is not None:
        print("formal_tlc.py: --find/--replace is deprecated; use --symbol, --match, --op and --with", file=sys.stderr)
        if args.replace is None:
            raise coderef.AnchorError("--find needs --replace")
        edit = {"op": "replace", "path": name, "find": args.find, "replace": args.replace}
        return edit, coderef.edit_text(text, edit)
    if not (args.symbol or args.match):
        raise coderef.AnchorError("a control needs --symbol or --match (an anchor edit)")
    edit = coderef.cli_edit(name, args.op, args.symbol, args.match, args.with_)
    return edit, coderef.apply_text(text, edit)


def cmd_control(args: argparse.Namespace) -> int:
    spec = Path(args.spec).resolve()
    tmp = Path(tempfile.mkdtemp(prefix="tlc-control-"))
    try:
        for f in spec.parent.iterdir():
            if f.is_file() and f.suffix in (".tla", ".cfg"):
                shutil.copy2(f, tmp / f.name)
        planted = tmp / spec.name
        text = planted.read_text(encoding="utf-8")
        try:
            edit, after = plant(args, spec.name, text)
        except coderef.AnchorError as exc:
            print(json.dumps({"status": "error", "note": f"ANCHOR ERROR: {exc}"}))
            return 2
        planted.write_text(after, encoding="utf-8")
        cfg = tmp / Path(args.cfg).name if args.cfg else None
        res = run(planted, cfg, not args.no_deadlock_check)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    matched = None
    if res["status"] == "red" and args.pattern:
        matched = re.search(args.pattern, str(res["output_tail"]) + json.dumps(res["violation"])) is not None
    res["control"] = {"edit": edit, "pattern": args.pattern, "matched": matched}
    print(json.dumps(res, indent=2))
    if res["status"] == "red" and matched is not False:
        return 0
    return 1 if res["status"] == "green" else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "dump", "vectors", "control"):
        p = sub.add_parser(name)
        p.add_argument("--spec", required=True)
        p.add_argument("--cfg", required=(name in ("dump", "vectors")))
        p.add_argument("--no-deadlock-check", action="store_true",
                       help="pass -deadlock to TLC (turns the deadlock check off)")
        if name in ("dump", "vectors"):
            p.add_argument("--out", required=True)
        if name == "vectors":
            p.add_argument("--done", action="append", required=True)
            p.add_argument("--keep", action="append", help="keep only these variables in each vector")
            p.add_argument("--check", action="store_true")
        if name == "control":
            p.add_argument("--symbol", help="a definition name (`Name ==`)")
            p.add_argument("--match", help='a literal, or "/RE/"; it must occur once in the definition')
            p.add_argument("--op", choices=coderef.ANCHOR_OPS)
            p.add_argument("--with", dest="with_", help="the new text (replace-with)")
            p.add_argument("--find", help="deprecated: use the anchor flags")
            p.add_argument("--replace", help="deprecated: use the anchor flags")
            p.add_argument("--pattern")
    args = ap.parse_args()
    return {"check": cmd_check, "dump": cmd_dump, "vectors": cmd_vectors,
            "control": cmd_control}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
