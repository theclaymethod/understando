#!/usr/bin/env python3
"""Turn a witness from a stuck proof or a TLC trace into a regression test, and route the blocker.

    python3 scripts/formal_witness.py test  --witness W.json --claim EXPR --out tests/test_witness_x.py
                                            [--style unittest|pytest] [--route code-first]
    python3 scripts/formal_witness.py route --attempt ATTEMPT.json [--witness W.json] [--model-is-code]

test   W.json is {"function": "pkg.mod.fn", "args": {...}, "model_output": ...}. EXPR is a Python
       expression over the argument names and `result` (the real function's return value) that the
       claim says holds, for example "sum(result) == total". The test calls the real function on
       the witness input and asserts EXPR. On a code-first blocker it fails on the bug and passes
       once the bug is fixed: it is the regression test the PR author gets.
route  reads a proof attempt (formal_lean.py attempt) and an optional witness, and prints the
       route with its reason and Bayes factor. A concrete witness on a model that transcribes the
       code is code-first (BF 8). A witness on a model that abstracts the code is model-first until
       the witness replays red on the real code. No witness: code-first under uncertainty (the
       loss matrix), with a witness search as the next action.
"""

from __future__ import annotations

import argparse
import json
import keyword
import sys
from pathlib import Path


def cmd_test(args: argparse.Namespace) -> int:
    w = json.loads(Path(args.witness).read_text())
    module, _, fn = w["function"].rpartition(".")
    names = list(w["args"])
    if not all(n.isidentifier() and not keyword.iskeyword(n) for n in names):
        raise SystemExit("witness argument names must be identifiers")
    binds = "".join(f"    {n} = {w['args'][n]!r}\n" for n in names)
    call = f"{fn}({', '.join(f'{n}={n}' for n in names)})"
    shown = ", ".join(f"{n}={w['args'][n]!r}" for n in names)
    doc = (f'"""Regression test from a formal witness (route: {args.route}).\n\n'
           f"Claim: {args.claim}\nWitness: {fn}({shown}); the model of the code returned "
           f"{w.get('model_output')!r}.\nIt fails while the bug is in the code.\n\"\"\"\n\n")
    body = f"{binds}    result = {call}\n"
    msg = f'f"{fn}({shown}) returned {{result!r}}; the claim {args.claim} does not hold"'
    if args.style == "pytest":
        text = (doc + f"from {module} import {fn}\n\n\n"
                f"def test_{fn}_witness() -> None:\n{body}    assert {args.claim}, {msg}\n")
    else:
        text = (doc + f"import unittest\n\nfrom {module} import {fn}\n\n\n"
                f"class WitnessTest(unittest.TestCase):\n    def test_{fn}_witness(self) -> None:\n"
                + "".join("    " + line + "\n" for line in body.splitlines())
                + f"        self.assertTrue({args.claim}, {msg})\n")
    Path(args.out).write_text(text, encoding="utf-8")
    print(json.dumps({"test": args.out, "function": w["function"], "args": w["args"], "claim": args.claim}))
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    attempt = json.loads(Path(args.attempt).read_text())
    witness = json.loads(Path(args.witness).read_text()) if args.witness else None
    tail = str(attempt.get("output_tail", ""))
    if attempt.get("status") == "green":
        out = {"route": "none", "reason": "the proof builds", "bayes_factor": None}
    elif witness:
        if args.model_is_code:
            out = {"route": "code-first", "bayes_factor": 8.0,
                   "reason": "a concrete counterexample on a model that transcribes the code"}
        else:
            out = {"route": "model-first", "bayes_factor": 4.0,
                   "reason": "a counterexample on an abstract model: replay it on the real code; red there makes it code-first"}
    elif "is false" in tail or "counterexample" in tail:
        out = {"route": "code-first", "bayes_factor": 8.0,
               "reason": "Lean refuted the statement; extract the witness next"}
    else:
        out = {"route": "code-first", "bayes_factor": None,
               "reason": "no witness yet; bias code-first under uncertainty and search for a witness"}
    out["blocker"] = tail.splitlines()[0] if tail else ""
    print(json.dumps(out, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("test")
    p.add_argument("--witness", required=True)
    p.add_argument("--claim", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--style", choices=["unittest", "pytest"], default="unittest")
    p.add_argument("--route", default="code-first")
    p = sub.add_parser("route")
    p.add_argument("--attempt", required=True)
    p.add_argument("--witness")
    p.add_argument("--model-is-code", action="store_true")
    args = ap.parse_args()
    return {"test": cmd_test, "route": cmd_route}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
