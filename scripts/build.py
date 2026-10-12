"""understando build: verifier-driven development for one feature. Each step has a completion criterion.

    understando build [--feature F]                          the steps and whether each one is done
    understando build claim --invariant I1 [--risky] [--text T]   step 2: the claim, and the check the bar asks for
    understando build check --claim C1 --kind KIND --command "ARGV" [--code PATH::SYMBOL] [--name N]
                            [--evidence GLOB,GLOB] [--score RE --frozen JUDGE] [--cc-id ID]   step 3
    understando build red --check V1 (--at REF | --stub PATH@REF | --plant EDIT_JSON) [--yes]  step 4
    understando build green --check V1 [--yes]               step 5
    then `understando probe --feature F`                     step 6

1. invariant: the user stated it (discover). Done when the feature has an accepted invariant.
2. pick: the strongest practical check on the ladder (e2e < property < types/contracts < TLA+ <
   Lean with conformance), from the shape of the invariant and the bar of the feature's surface
   (references/evidence-bars.md). Done when each claim has a plan.
3. write the check. Done when each claim has a check with a command.
4. prove that it fails: on the current code (the check comes before the code), on a stub, or on a
   planted bug. A planted bug or a stub becomes a control of the check, so probe runs it again.
   Done when each check went red.
5. write the code until the check passes. Done when each check is green at the head.
6. probe. Done when each check is proven (strength.py).

The checks run at a commit in a scratch copy: commit the check and the code first. Each run shows
its command and runs only with --yes.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import ops  # noqa: E402
import probe  # noqa: E402
import run_control  # noqa: E402
import store  # noqa: E402
import strength  # noqa: E402

def plan(data: dict, claim: dict) -> dict:
    """The check kind for a claim (strength.plan), from its feature's surface and its invariants."""
    feat = store.find(data, "features", claim.get("feature")) or {}
    invs = [store.find(data, "invariants", i) or {} for i in claim.get("invariants", [])]
    shape = next((i.get("shape") for i in invs if i.get("shape")), "input-space")
    risky = bool(claim.get("risky") or any(i.get("risky") for i in invs))
    return strength.plan(feat.get("surface", "other"), risky, shape)


def steps(data: dict, feature: str | None) -> list[dict]:
    claims = [cl for cl in data["claims"] if not feature or cl.get("feature") == feature]
    invs = [i for i in data["invariants"] if not feature or i.get("feature") == feature]
    checks = [v for v in data["checks"] if v["id"] in {x for cl in claims for x in cl["checks"]}]
    rep = strength.apply(data)
    proven = {x["id"] for x in data["checks"] if x["state"] == "proven"}
    bar = {x["id"]: x for x in rep["claims"]}
    return [
        {"step": "invariant", "done": any(i["status"] == "accepted" for i in invs),
         "how": "understando discover --feature F, then discover answer (the user states each invariant)"},
        {"step": "pick", "done": bool(claims) and all(cl.get("plan") for cl in claims),
         "how": "understando build claim --invariant I1 (it names the check that the bar asks for)"},
        {"step": "check", "done": bool(claims) and all(cl["checks"] for cl in claims),
         "how": "write the check, then understando build check --claim C1 --kind KIND --command \"...\""},
        {"step": "red", "done": bool(checks) and all((v.get("red_first") or {}).get("status") == "red" for v in checks),
         "how": "understando build red --check V1 --at HEAD | --stub PATH@REF | --plant EDIT_JSON"},
        {"step": "green", "done": bool(checks) and all((v.get("baseline") or {}).get("status") == "green" for v in checks),
         "how": "write the code, commit it, then understando build green --check V1"},
        {"step": "probe", "done": bool(checks) and all(v["id"] in proven for v in checks) and all(bar[cl["id"]]["bar_met"] for cl in claims),
         "how": "understando probe --feature F (each check proven, and each claim at its bar)"},
    ]


def add_claim(data: dict, inv_id: str, risky: bool, text: str | None) -> dict:
    inv = store.need(data, "invariants", inv_id)
    if inv["status"] in ("rejected", "deferred"):
        store.fail(f"build claim: {inv_id} is {inv['status']}", 2)
    cl = next((x for x in data["claims"] if x.get("invariants") == [inv_id]), None)
    if not cl:
        cl = {"id": store.next_id(data, "claims"), "text": text or inv["text"], "invariants": [inv_id], "checks": [],
              **({"feature": inv["feature"]} if inv.get("feature") else {}), **({"code": inv["code"]} if inv.get("code") else {})}
        data["claims"].append(cl)
    if risky:
        cl["risky"] = True
    if text:
        cl["text"] = text
    import ste
    try:
        ste.require([cl["text"]], f"build claim {cl['id']}")
    except ste.SteMissing as exc:
        store.fail(str(exc), 1)
    except ValueError as exc:
        store.fail(str(exc), 2)
    cl["plan"] = plan(data, cl)
    return cl


def add_check(data: dict, args: argparse.Namespace) -> dict:
    cl = store.need(data, "claims", args.claim)
    v = {"id": store.next_id(data, "checks"), "kind": args.kind, "name": args.name or f"{args.kind} check of {cl['id']}",
         **({"feature": cl["feature"]} if cl.get("feature") else {})}
    if args.command:
        v["command"] = {"argv": shlex.split(args.command), **({"cwd": args.cwd} if args.cwd else {})}
    if args.code:
        path, _, sym = args.code.partition("::")
        v["code"] = [{"path": path, **({"symbol": sym} if sym else {})}]
    if args.evidence:
        v["evidence"] = {"require": [g for g in args.evidence.split(",") if g]}
    if args.score or args.frozen:
        v["eval"] = {**({"score": args.score} if args.score else {}), **({"frozen": args.frozen} if args.frozen else {}),
                     "better": args.better}
    if args.cc_id:
        v["cc_id"] = args.cc_id
    data["checks"].append(v)
    cl["checks"].append(v["id"])
    want = (cl.get("plan") or {}).get("kind")
    if want and store.LADDER.get(args.kind, 0) < store.LADDER.get(want, 0):
        print(f"build: {v['id']} is a {args.kind} check; the bar of {cl['id']} asks for {want} ({cl['plan']['why']}). "
              "It counts, but the claim stays below its bar until a stronger check is proven.")
    return v


def red(c: store.Ctx, data: dict, v: dict, at: str | None, stub: str | None, plant: str | None) -> bool:
    """Step 4: the check must go red on the current code, a stub or a planted bug."""
    repo = c.need_repo()
    if "command" not in v:
        store.fail(f"build red: {v['id']} has no command", 2)
    if not store.confirm(c, f"build red {v['id']}", [s["argv"] for s in data.get("setup", [])] + [v["command"]["argv"]]):
        return False
    if plant or stub:
        if stub:
            path, _, ref = stub.partition("@")
            edit = {"op": "restore-file", "path": path, "at": store.git(repo, "rev-parse", ref or "HEAD")}
            kind, what = "stub", f"The code of {path} as it was at {ref}: the stub without the feature."
        else:
            edit = json.loads(plant)
            kind, what = "planted", "A planted bug from build red."
        k = {"id": store.next_id(data, "controls"), "check": v["id"], "kind": kind, "description": what,
             "edits": [edit], "expect": {"status": "red"}}
        data["controls"].append(k)
        with ops.scratch_clone(repo) as (clone, wt):
            run_control.run_one(data, k, clone, wt)
        v["red_first"] = {**k["result"], "note": f"control {k['id']} ({kind})"}
    else:
        commit = store.git(repo, "rev-parse", at or "HEAD")
        with ops.scratch_clone(repo) as (clone, wt):
            with run_control.Worktree(clone, commit, wt, "red") as root:
                run_control.prepare(root, data)
                code, out, seconds = run_control.run_command(root, v["command"])
        v["red_first"] = {"status": run_control.classify(code, v["command"]), "exit": code, "seconds": seconds,
                          "output_tail": run_control.tail(run_control.scrub(out, root)), "ran_at": store.now(), "head": commit,
                          "note": f"the check at {commit[:10]}, before the code"}
    st = v["red_first"]["status"]
    print(f"build red {v['id']}: {st}" + ("" if st == "red" else ". The check did not fail, so it cannot prove the code yet. "
                                          "Make it fail first: test the behaviour that the code must add."))
    return True


def main(c: store.Ctx, argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="understando build", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", nargs="?", default="status", choices=["status", "claim", "check", "red", "green"])
    ap.add_argument("--feature")
    ap.add_argument("--invariant")
    ap.add_argument("--risky", action="store_true")
    ap.add_argument("--text")
    ap.add_argument("--claim")
    ap.add_argument("--kind", choices=sorted(store.LADDER))
    ap.add_argument("--command")
    ap.add_argument("--cwd")
    ap.add_argument("--code", help="PATH::SYMBOL of the test or spec")
    ap.add_argument("--name")
    ap.add_argument("--evidence", help="frontend: the files a run must leave, for example '*.webm,*.png'")
    ap.add_argument("--score", help="llm: a regex with one group, the score in the output")
    ap.add_argument("--frozen", help="llm: the frozen judge or the labels file")
    ap.add_argument("--better", choices=["higher", "lower"], default="higher")
    ap.add_argument("--cc-id", help="the @cc contract that states the invariant")
    ap.add_argument("--check")
    ap.add_argument("--at")
    ap.add_argument("--stub", help="PATH@REF: the file as it was at REF")
    ap.add_argument("--plant", help="a control edit as JSON (references/controls.md)")
    args = ap.parse_args(argv)
    data = c.need_data()
    if args.action == "status":
        rows = steps(data, args.feature)
        nxt = next((r for r in rows if not r["done"]), None)
        text = "\n".join(f"  [{'x' if r['done'] else ' '}] {n}. {r['step']}" + ("" if r["done"] else f": {r['how']}") for n, r in enumerate(rows, 1))
        store.emit(c, {"steps": rows, "next": nxt and nxt["step"]}, f"build{' ' + args.feature if args.feature else ''}:\n{text}"
                   + ("\nDONE: every step holds." if not nxt else f"\nnext: {nxt['step']}"))
        return 0
    if args.action == "claim":
        if not args.invariant:
            store.fail("build claim: pass --invariant I1", 2)
        cl = add_claim(data, args.invariant, args.risky, args.text)
        c.save(data)
        inv = store.find(data, "invariants", args.invariant)
        note = "" if inv["author"] == "user" else " The invariant is agent-picked: the claim stays Backed until the user accepts it."
        store.emit(c, cl, f"claim {cl['id']}: {cl['text']}\nplan: a {cl['plan']['kind']} check. {cl['plan']['why']}.{note}")
        return 0
    if args.action == "check":
        if not (args.claim and args.kind):
            store.fail("build check: pass --claim and --kind", 2)
        v = add_check(data, args)
        c.save(data)
        store.emit(c, v, f"check {v['id']} for {args.claim}: {v['name']}. Next: understando build red --check {v['id']}")
        return 0
    v = store.need(data, "checks", args.check)
    repo = c.need_repo()
    data["head"] = store.git(repo, "rev-parse", "HEAD")
    if args.action == "red":
        if not red(c, data, v, args.at, args.stub, args.plant):
            return 0
        c.save(data)
        return 0 if v["red_first"]["status"] == "red" else 1
    if not probe.run(c, data, {v["id"]}, set(), what=f"build green {v['id']}"):
        return 0
    c.save(data)
    st = v["baseline"]["status"]
    print(f"build green {v['id']}: {st}" + ("" if st == "green" else ": write the code until the check passes, commit it, and run this again."))
    return 0 if st == "green" else 1
