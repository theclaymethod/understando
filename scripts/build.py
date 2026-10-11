"""understando build: the verifier-first playbook for new work (commands/build.md).

    understando build [status]                                  each step and its completion state
    understando build claim --invariant I01 [--cc-id ID] [--tier N] [--promise P1]
    understando build verifier --claim C01 --spec FILE          add a verifier and its control
    understando build red-first --verifier V01 --at REF         run it before the code exists: it must go red

The steps that are unique to understando: 1 discover, 2 the @cc contract, 3 the verifier,
proven red before the code exists, 4 the code until green, 5 probe, 6 the ready gates, 7 explain.
For the general feature workflow, route to Poteto Mode's Feature playbook or tdd when present,
else to references/adapted/feature-playbook.md and tdd-red-first.md. `claim` and `verifier`
refuse an invariant that the user has not confirmed, except under full autonomy, where the
claim stays at Backed.

--spec holds {"verifier": {"kind", "description", "command": {"argv"}, "test"?, "ladder"?},
"control": {"description", "edits", "expect"}}.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ctx as context  # noqa: E402
import discover  # noqa: E402
import journal  # noqa: E402
import ops  # noqa: E402
import run_control  # noqa: E402
import tm  # noqa: E402
import verdicts  # noqa: E402

STEPS = [
    ("discover", "Run `understando discover` until every candidate has a decision."),
    ("contract", "Write each confirmed invariant as an @cc contract, then `understando build claim --invariant I01 --cc-id ID`."),
    ("verifier", "Write the verifier at the strongest practical tier, then `build verifier` and `build red-first`: it goes red before the code exists."),
    ("code", "Write the code until each verifier is green at the head."),
    ("probe", "Run `understando probe`: each verifier goes red on a planted bug."),
    ("gates", "Run `understando ready`: all four gates pass."),
    ("explain", "Run `understando explain`."),
]


def status(c: context.Ctx) -> list[dict]:
    data = c.data() or {"claims": [], "verifiers": [], "controls": []}
    claims, vs = data["claims"], data["verifiers"]
    by_claim = {cl["id"]: [v for v in vs if cl["id"] in v["claims"]] for cl in claims}
    d = discover.status(c) if c.run else {"done": False}
    ready = json.loads((c.run / "ready.json").read_text()) if c.run and (c.run / "ready.json").is_file() else {}
    done = {
        "discover": d.get("done", False),
        "contract": bool(claims) and all(cl.get("cc_id") and (cl.get("stated") or ops.confirmed_invariant(data, cl.get("invariant"))) for cl in claims),
        "verifier": bool(claims) and all(any((v.get("red_first") or {}).get("status") == "red" for v in by_claim[cl["id"]]) for cl in claims),
        "code": bool(vs) and all((v.get("baseline") or {}).get("status") == "green" for v in vs if "command" in v),
        "probe": bool(vs) and all(v.get("state") == "proven" for v in vs if "command" in v),
        "gates": bool(ready.get("pass")) and ready.get("head") == data.get("head"),
        "explain": bool(c.run) and (c.run / "explainer.mdx").is_file(),
    }
    return [{"step": i, "name": n, "done": done[n], "how": how} for i, (n, how) in enumerate(STEPS, 1)]


def add_claim(c: context.Ctx, inv_id: str, cc_id: str | None, tier: int | None, promise: str | None) -> str:
    data = c.need_map()
    inv = ops.confirmed_invariant(data, inv_id)
    if not inv and ops.autonomy():
        inv = next((i for i in data.get("invariants", []) if i["id"] == inv_id and i["author"] == "agent"), None)
    if not inv:
        tm.fail(f"refuse: invariant {inv_id} has no user-confirmed row (author user, accepted). Run `understando discover` first.", 1)
    cid = ops.next_id(data, "C")
    data["claims"].append({"id": cid, "cc_id": cc_id, "text": inv["text"], "stated": False, "invariant": inv_id,
                           "source": f"understando build, from invariant {inv_id}", "tier_target": tier or inv.get("tier", 1),
                           "plain": {"what": inv["text"], "proof": "No check yet. build writes the verifier next."}})
    if promise:
        p = next((p for p in data.get("promises", []) if p["id"] == promise), None)
        if not p:
            tm.fail(f"build: no promise {promise}", 2)
        p["claims"].append(cid)
    tm.save(data, c.map)
    return cid


def add_verifier(c: context.Ctx, claim_id: str, spec_path: str) -> str:
    data = c.need_map()
    claim = next((x for x in data["claims"] if x["id"] == claim_id), None)
    if not claim:
        tm.fail(f"build: no claim {claim_id}", 2)
    refusal = ops.intent_ok(data, claim)
    if refusal:
        tm.fail(refusal, 1)
    spec = json.loads(Path(spec_path).read_text())
    vid, kid = ops.next_id(data, "V"), ops.next_id(data, "K")
    v = {"id": vid, "claims": [claim_id], "tier": "fact", "independence": {"by": "tool", "tool": spec["verifier"]["command"]["argv"][0]},
         "cost": {"usd": 0}, "provenance": "Written by understando build, verifier first.", **spec["verifier"]}
    data["verifiers"].append(v)
    data["controls"].append({"id": kid, "verifier": vid, "recipe": spec["control"].get("recipe", "plant-violation"),
                             "description": spec["control"]["description"], "edits": spec["control"]["edits"],
                             "expect": spec["control"]["expect"]})
    tm.save(data, c.map)
    return vid


def red_first(c: context.Ctx, vid: str, ref: str) -> dict:
    data, repo = c.need_map(), c.need_repo()
    v = next((x for x in data["verifiers"] if x["id"] == vid), None)
    if not v or "command" not in v:
        tm.fail(f"build: no verifier {vid} with a command", 2)
    claim = next(x for x in data["claims"] if x["id"] in v["claims"])
    refusal = ops.intent_ok(data, claim)
    if refusal:
        tm.fail(refusal, 1)
    commit = ops.git(repo, "rev-parse", ref)
    with ops.scratch_clone(repo) as (clone, wt):
        with run_control.Worktree(clone, commit, wt, "red-first") as root:
            run_control.prepare(root, data)
            code, output, _ = run_control.run_command(root, v["command"], None)
    status = run_control.classify(code, v["command"])
    v["red_first"] = {"status": status, "at": commit, "exit": code, "output_tail": run_control.tail(output), "ran_at": tm.now()}
    tm.save(data, c.map)
    return v["red_first"]


def main(c: context.Ctx, argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="understando build", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", nargs="?", default="status", choices=["status", "claim", "verifier", "red-first"])
    ap.add_argument("--invariant")
    ap.add_argument("--cc-id")
    ap.add_argument("--tier", type=int)
    ap.add_argument("--promise")
    ap.add_argument("--claim")
    ap.add_argument("--spec")
    ap.add_argument("--verifier")
    ap.add_argument("--at")
    args = ap.parse_args(argv)
    if args.action == "claim":
        cid = add_claim(c, args.invariant, args.cc_id, args.tier, args.promise)
        journal.append(c.journal, "decision", f"build: claim {cid} from invariant {args.invariant}", c.repo, claims=[cid])
        context.emit(c, {"claim": cid}, f"build: claim {cid} states invariant {args.invariant}")
    elif args.action == "verifier":
        vid = add_verifier(c, args.claim, args.spec)
        journal.append(c.journal, "verifier-choice", f"build: verifier {vid} for {args.claim}", c.repo, claims=[args.claim])
        context.emit(c, {"verifier": vid}, f"build: verifier {vid} for {args.claim}. Next: understando build red-first --verifier {vid} --at <stub commit>")
    elif args.action == "red-first":
        r = red_first(c, args.verifier, args.at)
        ok = r["status"] == "red"
        context.emit(c, r, f"build: {args.verifier} is {r['status']} at {r['at'][:10]}. " +
                     ("Good: it fails before the code exists." if ok else "It must go red before the code exists. Fix the verifier or the stub."))
        return 0 if ok else 1
    else:
        rows = status(c)
        text = "\n".join(f"[{'x' if r['done'] else ' '}] {r['step']} {r['name']}: {r['how']}" for r in rows)
        nxt = next((r for r in rows if not r["done"]), None)
        context.emit(c, {"steps": rows}, text + (f"\nnext: step {nxt['step']} {nxt['name']}" if nxt else "\nall steps done"))
    return 0
