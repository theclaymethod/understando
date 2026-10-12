#!/usr/bin/env python3
"""Assemble a formal artifact record, rate it Formal or not, gate it on drift, and add it to a sidecar.

    python3 scripts/formal_record.py build  --out R.json --id F01 --kind lean|tla|property --tier 2|4|5
                                            --claim C01 [--claim ...] --description TEXT
                                            --check CHECK.json --conformance RUN.json
                                            [--control model:K01:CTRL.json[:PROP]] [--control code:K02:RUN.json[:PROP]]
                                            [--property PROP=C01[=CHECK NAME] ...]
                                            [--card CARD.json] [--checks7 CHECKS.json]
                                            [--route none|code-first|model-first|harness-first|theorem-first]
                                            [--witness W.json] [--witness-test RUN.json]
    python3 scripts/formal_record.py stamp  --record R.json --repo DIR --code PATH... --model PATH...
    python3 scripts/formal_record.py drift  --record R.json --repo DIR
    python3 scripts/formal_record.py verdict --record R.json
    python3 scripts/formal_record.py add    --sidecar S.json --record R.json --repo NAME --head SHA [--app APP]

Inputs are the JSON results that formal_lean.py, formal_tlc.py and formal_run.py print.

Formal holds only when all of these hold (`verdict` lists each one that is missing):
  - the tier is 4 or 5, and the check is green: Lean builds with no sorry, admit or new axiom and
    each theorem depends only on propext, Quot.sound and Classical.choice; or TLC finished with no
    error, with the deadlock check on;
  - the conformance run against the real code is green, and every check of the 7-check pass that
    applies is "pass";
  - at least one model control (a planted wrong model or spec) is red; for tier 5, at least one
    code control (a planted wrong function) is red too; and no control is green or error;
  - the drift block is stamped;
  - the invariant is user-confirmed: `invariant.author` is "user" and `invariant.ref` names the
    invariant that the user accepted in `discover`. When only this one is missing, the
    verdict is "Formal (pending user confirmation)": an agent-proposed invariant is never Formal.

Field names of a record: id, kind, ladder_tier, claims, description, card, check, conformance
{result, checks}, controls [{id, target, result, property?, map_id?}], properties [{name, part,
check_name?, check?, controls}], route, blocker_open, invariant {author, ref, status, items}, witness, witness_test, drift {commit,
code_files [{path, blob}], model_files [{path, sha256}], root}, formal {verdict, missing}. Each
result keeps `rerun`: the helper call that made it, so `understando formalize --recheck` can run
it again. Standard
library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))  # also under python3 -I, which drops the script folder
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)

CHECKS7 = ("statement_parity", "state_parity", "transition_parity", "concurrency_parity",
           "cancel_drain_parity", "runtime_evidence", "drift_gate")
SIDE_SCHEMA = "understando.formal/1"


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path: str | Path, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def trim(result: dict) -> dict:
    """Keep a result small: the status, the counts, the hashes, the violation and its trace."""
    keep = ("status", "exit", "seconds", "matched", "violation", "trace", "generated", "distinct", "spec",
            "spec_sha256", "cfg", "cfg_sha256", "deadlock_checked", "theorems", "forbidden",
            "tree_sha256", "files", "why", "control", "argv", "edits", "output_tail", "rerun")
    out = {k: result[k] for k in keep if k in result}
    if isinstance(out.get("output_tail"), str):
        out["output_tail"] = re.sub(r"/(?:private/)?var/folders/\S+?/T/", "<tmp>/", out["output_tail"].replace(str(Path.home()), "~"))
    return out


def cmd_build(args: argparse.Namespace) -> int:
    controls = []
    for spec in args.control:
        target, cid, path, *prop = spec.split(":", 3)
        controls.append({"id": cid, "target": target, "result": trim(load(path)), **({"property": prop[0]} if prop else {})})
    properties = []
    for spec in args.property:
        name, _, rest = spec.partition("=")
        part, _, check_name = rest.partition("=")
        if not (name and part):
            raise SystemExit(f"--property {spec}: write NAME=PART or NAME=PART=CHECK NAME")
        properties.append({"name": name, "part": part, **({"check_name": check_name} if check_name else {}),
                           "controls": [k["id"] for k in controls if k.get("property") == name]})
    record = {
        "id": args.id,
        "kind": args.kind,
        "ladder_tier": args.tier,
        "claims": args.claim,
        "description": args.description,
        "card": load(args.card) if args.card else None,
        "check": trim(load(args.check)),
        "conformance": {
            "result": trim(load(args.conformance)),
            "checks": load(args.checks7) if args.checks7 else None,
        },
        "controls": controls,
        "route": args.route,
        "blocker_open": args.blocker_open,
        "invariant": {"author": args.invariant_author, "ref": args.invariant_ref, "status":
                      "confirmed" if args.invariant_author == "user" and args.invariant_ref else "proposed",
                      "items": load(args.invariants) if args.invariants else []},
        "witness": load(args.witness) if args.witness else None,
        "witness_test": trim(load(args.witness_test)) if args.witness_test else None,
        "independence": {"by": "tool", "tool": {"lean": "lean", "tla": "tlc", "property": "property"}[args.kind]},
        "cost": {"usd": 0},
    }
    if properties:
        record["properties"] = properties
    record["formal"] = rate(record)
    save(args.out, record)
    print(json.dumps(record["formal"]))
    return 0


def rate(r: dict) -> dict:
    missing = []
    if r.get("ladder_tier") not in (4, 5):
        missing.append("tier below 4")
    check = r.get("check") or {}
    if check.get("status") != "green":
        missing.append("the proof or model check is not green")
    if r.get("kind") == "lean":
        bad = [t for t, v in (check.get("theorems") or {}).items() if not v.get("axioms_clean")]
        if not check.get("theorems") or bad or check.get("forbidden"):
            missing.append("axioms not clean, or sorry/admit/axiom in the source")
    if r.get("kind") == "tla" and check.get("deadlock_checked") is not True:
        missing.append("TLC ran without the deadlock check")
    conf = r.get("conformance") or {}
    if (conf.get("result") or {}).get("status") != "green":
        missing.append("conformance with the real code is not green")
    checks = conf.get("checks") or {}
    failed = [k for k in CHECKS7 if (checks.get(k) or {}).get("status", "missing") not in ("pass", "n/a")]
    if failed:
        missing.append("7-check pass not complete: " + ", ".join(failed))
    controls = r.get("controls") or []
    if any(c["result"].get("status") != "red" for c in controls):
        missing.append("a control is not red: the verifier cannot fail there")
    if not any(c["target"] == "model" and c["result"].get("status") == "red" for c in controls):
        missing.append("no red model control")
    if r.get("ladder_tier") == 5 and not any(c["target"] == "code" and c["result"].get("status") == "red"
                                             for c in controls):
        missing.append("no red code control")
    if not r.get("drift"):
        missing.append("drift block not stamped")
    if r.get("blocker_open"):
        missing.append(f"open blocker, route {r.get('route')}")
    if missing:
        return {"verdict": "Not formal", "missing": missing}
    inv = r.get("invariant") or {}
    if inv.get("author") != "user" or not inv.get("ref"):
        return {"verdict": "Formal (pending user confirmation)",
                "missing": ["no user-confirmed invariant (an invariant that the user accepted in discover)"]}
    return {"verdict": "Formal", "missing": []}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def blob(repo: Path, path: str) -> str:
    """The blob of the working-tree file, as git would store it."""
    return git(repo, "hash-object", path)


def stamp_of(repo: Path, code: list[str], model: list[str]) -> dict:
    return {
        "commit": git(repo, "rev-parse", "HEAD"),
        "root": str(repo),
        "code_files": [{"path": p, "blob": blob(repo, p)} for p in code],
        "model_files": [{"path": p, "sha256": "sha256:" + hashlib.sha256((repo / p).read_bytes()).hexdigest()}
                        for p in model],
    }


def cmd_stamp(args: argparse.Namespace) -> int:
    record = load(args.record)
    record["drift"] = stamp_of(Path(args.repo).resolve(), args.code, args.model)
    record["formal"] = rate(record)
    save(args.record, record)
    print(json.dumps({"drift": record["drift"]["commit"], "formal": record["formal"]["verdict"]}))
    return 0


def cmd_drift(args: argparse.Namespace) -> int:
    record = load(args.record)
    old = record.get("drift")
    if not old:
        print(json.dumps({"status": "red", "why": "no drift stamp"}))
        return 1
    repo = Path(args.repo).resolve()
    new = stamp_of(repo, [f["path"] for f in old["code_files"]], [f["path"] for f in old["model_files"]])
    changed = [a["path"] for a, b in zip(old["code_files"] + old["model_files"], new["code_files"] + new["model_files"])
               if a != b]
    status = "green" if not changed else "red"
    print(json.dumps({"status": status, "changed": changed, "stamped_at": old["commit"], "now": new["commit"]}))
    return 0 if status == "green" else 1


def cmd_verdict(args: argparse.Namespace) -> int:
    record = load(args.record)
    record["formal"] = rate(record)
    save(args.record, record)
    print(json.dumps({"id": record["id"], **record["formal"]}, indent=2))
    return 0 if record["formal"]["verdict"] == "Formal" else 1


def cmd_add(args: argparse.Namespace) -> int:
    path = Path(args.sidecar)
    side = load(str(path)) if path.exists() else {"schema": SIDE_SCHEMA, "repo": args.repo, "app": args.app,
                                                 "head": args.head, "verifiers": []}
    record = load(args.record)
    keep_keys(side, record)
    links = {c["id"]: c["claim"] for c in side.get("proposed_claims", []) if c.get("claim")}
    if args.proposed_claims:
        new = load(args.proposed_claims)
        keep = [c for c in side.get("proposed_claims", []) if c["id"] not in {n["id"] for n in new}]
        side["proposed_claims"] = sorted(keep + [{**n, **({"claim": links[n["id"]]} if n["id"] in links and "claim" not in n else {})}
                                                 for n in new], key=lambda c: c["id"])
    side["verifiers"] = [v for v in side["verifiers"] if v["id"] != record["id"]] + [record]
    side["verifiers"].sort(key=lambda v: v["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    save(path, side)
    print(json.dumps({"sidecar": str(path), "verifiers": [v["id"] for v in side["verifiers"]]}))
    return 0


def keep_keys(side: dict, record: dict) -> None:
    """The keys that formalize --sidecar wrote stay when a record is added again: the properties
    with their check IDs and parts, and the map ID of each control."""
    old = next((v for v in side["verifiers"] if v["id"] == record["id"]), None)
    if not old:
        return
    if old.get("properties") and not record.get("properties"):
        record["properties"] = old["properties"]
    elif old.get("properties"):
        checks = {p["name"]: p.get("check") for p in old["properties"]}
        for p in record["properties"]:
            if checks.get(p["name"]) and not p.get("check"):
                p["check"] = checks[p["name"]]
    mids = {k["id"]: k["map_id"] for k in old.get("controls", []) if k.get("map_id")}
    for k in record.get("controls", []):
        if k["id"] in mids and not k.get("map_id"):
            k["map_id"] = mids[k["id"]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build")
    p.add_argument("--out", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--kind", choices=["lean", "tla", "property"], required=True)
    p.add_argument("--tier", type=int, choices=[2, 4, 5], required=True)
    p.add_argument("--claim", action="append", required=True)
    p.add_argument("--description", required=True)
    p.add_argument("--check", required=True)
    p.add_argument("--conformance", required=True)
    p.add_argument("--control", action="append", default=[], metavar="TARGET:ID:RESULT.json[:PROPERTY]",
                   help="a control result (target model or code); PROPERTY is the property that it breaks")
    p.add_argument("--property", action="append", default=[], metavar="NAME=PART[=CHECK NAME]",
                   help="one check for each property (a TLA+ invariant or property, or a Lean theorem group), under the claim or part that states it")
    p.add_argument("--card")
    p.add_argument("--checks7")
    p.add_argument("--route", default="none")
    p.add_argument("--invariant-author", choices=["user", "agent"], default="agent",
                   help="who stated the invariant: user (an accepted invariant from discover) or agent (proposed)")
    p.add_argument("--invariant-ref", help="the id of the user-accepted invariant (discover)")
    p.add_argument("--invariants", help="JSON list: each invariant as {id, sentence, checked_by, "
                   "questions [{ask, code_today, where, looks}]}, for the interview with the user")
    p.add_argument("--blocker-open", action="store_true",
                   help="the first hard blocker is not resolved (a code-first bug stays in the PR)")
    p.add_argument("--witness")
    p.add_argument("--witness-test")
    p = sub.add_parser("stamp")
    p.add_argument("--record", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--code", nargs="+", required=True)
    p.add_argument("--model", nargs="+", required=True)
    p = sub.add_parser("drift")
    p.add_argument("--record", required=True)
    p.add_argument("--repo", required=True)
    p = sub.add_parser("verdict")
    p.add_argument("--record", required=True)
    p = sub.add_parser("add")
    p.add_argument("--sidecar", required=True)
    p.add_argument("--record", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--app")
    p.add_argument("--head", required=True)
    p.add_argument("--proposed-claims", help="JSON list of {id, text, source} for claims that the store lacks")
    args = ap.parse_args()
    return {"build": cmd_build, "stamp": cmd_stamp, "drift": cmd_drift, "verdict": cmd_verdict,
            "add": cmd_add}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
