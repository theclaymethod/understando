"""understando formalize: the backend proof tier. Lean (rung 5) or TLA+ (rung 4), with conformance.

    understando formalize                         the claims whose plan is a proof, and the toolchains
    understando formalize --claim C1 [--tier 4|5] the route for one claim (commands/formalize.md)
    understando formalize --sidecar FILE          bring the formal records into the store (scripts/formal_sync.py)
    understando formalize --recheck RECORD [--sidecar FILE] [--yes]   run a record again at the current code

The proof work follows commands/formalize.md with the helpers formal_lean.py, formal_tlc.py,
formal_run.py, formal_witness.py and formal_record.py. A record is Formal only with a green check
(clean axioms, or TLC with its deadlock check), a green conformance run and a complete 7-check
pass, red controls (a wrong model, and for Lean a wrong function), a drift stamp, and an invariant
that the user accepted. An agent-picked invariant gives at most "Formal (pending user confirmation)".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import store  # noqa: E402
import strength  # noqa: E402
import toolprobe  # noqa: E402


def main(c: store.Ctx, argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="understando formalize", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--claim")
    ap.add_argument("--tier", type=int, choices=[4, 5])
    ap.add_argument("--sidecar")
    ap.add_argument("--recheck", metavar="RECORD")
    args = ap.parse_args(argv)
    import formal_sync
    if args.recheck:
        c.need_run()
        return formal_sync.recheck(c, args.recheck, args.sidecar)
    if args.sidecar:
        out = formal_sync.sync(c, args.sidecar)
        store.emit(c, out, "\n".join([f"formalize --sidecar: {'the store changed' if out['changed'] else 'the store is the same'}: "
                                      f"{len(out['checks'])} formal checks, {len(out['claims'])} proposed claims matched by key"] + out["report"]))
        return 0
    data = c.need_data()
    if not args.claim:
        tools = toolprobe.tool_status()
        rows = [x for x in data["claims"] if (x.get("plan") or {}).get("kind") in ("lean", "tla")]
        store.emit(c, {"targets": [x["id"] for x in rows], "toolchains": tools},
                   "formalize targets: " + (", ".join(f"{x['id']} ({x['plan']['kind']})" for x in rows) or "none")
                   + "\ntoolchains: " + ", ".join(f"{k} {'yes' if v else 'no'}" for k, v in tools.items()))
        return 0
    cl = store.need(data, "claims", args.claim)
    ok, agent = strength.intent(data, cl.get("invariants", []))
    tier = args.tier or (5 if (cl.get("plan") or {}).get("kind") != "tla" else 4)
    lines = [f"formalize {cl['id']}: rung {tier}. Read commands/formalize.md, then "
             + ("route to lean-formal-feedback-loop when it is installed, else references/lean-python.md." if tier == 5 else "references/tla.md.")]
    if not ok:
        lines.append(f"The invariant {', '.join(agent) or '(none linked)'} is agent-picked: the record can reach only "
                     "\"Formal (pending user confirmation)\" until the user accepts it (understando discover).")
    need = ["lake"] if tier == 5 else ["java", "tla2tools"]
    tools = toolprobe.tool_status(need)
    missing = [t for t in need if not tools[t]]
    if missing:
        lines.append("missing toolchains (install them yourself): " + ", ".join(missing))
    if toolprobe.find_skill("lean-formal-feedback-loop") and tier == 5:
        lines.append(f"lean-formal-feedback-loop: {toolprobe.find_skill('lean-formal-feedback-loop')}")
    store.emit(c, {"claim": cl["id"], "tier": tier, "intent": ok, "missing": missing}, "\n".join(lines))
    return 0
