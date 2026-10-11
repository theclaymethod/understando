"""understando import: record outside evidence, and check its format on every import.

    understando import KIND FILE --claim C01 --description TEXT [--conformance-source TEXT]

KIND is one of:
  show-me-your-work  a decision log TSV: the header ts, phase, decision, why, evidence, result
  lean               a Lean file: at least one theorem or lemma, and no `sorry`
  verify-feature     a verify-<app> feature file: a Feature line and at least one Scenario
  nemesis-review     a nemesis-review spec: Markdown with a heading and at least one claim line
  evo                an evo result: a JSON object
  impeccable         an impeccable snapshot: a JSON object

The checks read the shape only, so they pin no tool version. A file that fails its check is
recorded with status `stale`: it backs no claim, and doctor reports it. doctor checks each
imported file again, and a file that changed after the import is stale too.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import ctx as context  # noqa: E402
import journal  # noqa: E402
import ops  # noqa: E402
import tm  # noqa: E402
import verdicts  # noqa: E402

KINDS = {
    "show-me-your-work": {"kind": "measurement", "tier": "fact", "tool": "show-me-your-work"},
    "lean": {"kind": "lean", "tier": "fact", "tool": "lean"},
    "verify-feature": {"kind": "e2e", "tier": "fact", "tool": "verify skill"},
    "nemesis-review": {"kind": "eval", "tier": "guess", "tool": "nemesis-review"},
    "evo": {"kind": "eval", "tier": "fact", "tool": "evo"},
    "impeccable": {"kind": "eval", "tier": "guess", "tool": "impeccable"},
}


def check(kind: str, path: Path) -> dict:
    if not path.is_file():
        return {"ok": False, "detail": f"{path} is missing"}
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8", errors="replace")

    def res(ok: bool, detail: str) -> dict:
        return {"ok": ok, "detail": detail, "sha256": sha}

    if kind == "show-me-your-work":
        head = text.splitlines()[0].split("\t") if text.strip() else []
        want = ["ts", "phase", "decision", "why", "evidence", "result"]
        if head != want:
            return res(False, f"the header is {head[:6]}, not {want}")
        bad = [i for i, line in enumerate(text.splitlines()[1:], 2) if line and len(line.split("\t")) != len(want)]
        return res(not bad, "rows with a wrong cell count: " + ", ".join(map(str, bad[:5])) if bad else f"{len(text.splitlines()) - 1} rows")
    if kind == "lean":
        if not re.search(r"^\s*(theorem|lemma)\s", text, re.M):
            return res(False, "no theorem or lemma")
        if re.search(r"\bsorry\b", text):
            return res(False, "the file holds `sorry`, so a proof is not complete")
        return res(True, "theorems present, no sorry")
    if kind == "verify-feature":
        ok = re.search(r"^\s*Feature:", text, re.M) and re.search(r"^\s*Scenario( Outline)?:", text, re.M)
        return res(bool(ok), "a Feature and its Scenarios" if ok else "no Feature line, or no Scenario")
    if kind == "nemesis-review":
        ok = re.search(r"^#{1,3}\s+\S", text, re.M) and re.search(r"^\s*([-*]|\d+\.)\s+\S", text, re.M)
        return res(bool(ok), "a heading and claim lines" if ok else "no heading, or no claim line")
    if kind in ("evo", "impeccable"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return res(False, f"not JSON: {exc.msg}")
        return res(isinstance(data, dict), "a JSON object" if isinstance(data, dict) else "JSON, but not an object")
    return res(False, f"unknown kind {kind}")


def main(c: context.Ctx, argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="understando import", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=sorted(KINDS))
    ap.add_argument("file")
    ap.add_argument("--claim", required=True)
    ap.add_argument("--description", required=True)
    ap.add_argument("--conformance-source", help="lean: the recorded conformance run that ties the proof to the code")
    args = ap.parse_args(argv)
    data = c.need_map()
    claim = next((x for x in data["claims"] if x["id"] == args.claim), None)
    if not claim:
        tm.fail(f"import: no claim {args.claim}", 2)
    path = Path(args.file).expanduser().resolve()
    got = check(args.kind, path)
    meta = KINDS[args.kind]
    vid = ops.next_id(data, "V")
    v = {"id": vid, "kind": meta["kind"], "claims": [args.claim], "tier": meta["tier"], "description": args.description,
         "recorded": {"source": f"{args.kind} import of {path.name}", "result": got["detail"], "at": tm.now()},
         "independence": {"by": "tool", "tool": meta["tool"]}, "cost": {"usd": 0},
         "provenance": f"Imported by understando from {path}.",
         "import": {"kind": args.kind, "path": str(path), "sha256": got.get("sha256", ""), "status": "ok" if got["ok"] else "stale",
                    "detail": got["detail"], "checked_at": tm.now()}}
    if args.kind == "lean":
        v["formal"] = {"tool": "lean", "artifact": str(path),
                       "conformance": {"status": "pass" if args.conformance_source else "fail",
                                       "source": args.conformance_source or "no conformance run recorded"}}
    data["verifiers"].append(v)
    verdicts.apply(data)
    tm.save(data, c.map)
    journal.append(c.journal, "result", f"import {args.kind} {path.name} as {vid}: {'ok' if got['ok'] else 'stale'}", c.repo,
                   evidence=str(path), result=got["detail"], claims=[args.claim])
    context.emit(c, {"verifier": vid, **got}, f"import {args.kind}: {vid} is {'ok' if got['ok'] else 'STALE'} ({got['detail']}). {args.claim} is {claim['verdict']}.")
    return 0
