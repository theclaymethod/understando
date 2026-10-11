#!/usr/bin/env python3
"""Regroup the claims of a trust map: merge old claims into fewer claims (promise -> claim -> check).

    python3 scripts/regroup.py --map trust-map.json --proposal proposal.json --out NEW.json \
        [--explain explain.json --explain-out NEW-explain.json] [--refs refs.resolved.json] [--table]

The proposal holds the user's words: for each new claim its promise, `merges` (the old claim ids),
`name`, `text` and `plain`; for each promise its new `name` and, when it changes, its other fields;
and a plain `name` for each check. The script writes the merged map in shape 2: each new claim lists
the union of the checks, code refs and invariants of its old claims, the old ids as `legacy_ids`,
and the old statements as `parts` (each with its own intent, so a merge never lends intent to a part
that has none). Then it applies the verdicts and prints the safety proof:

  1. each old check is under exactly one new claim;
  2. each claim's strength is the strength of its weakest check, and its card names that check;
  3. the merge verdict and its blocker count are the same as before, or the change is listed.

Exit 0 when the proof holds, 1 when it does not, 2 on a bad proposal. It never writes the input map.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import derive  # noqa: E402
import onto  # noqa: E402
import tm  # noqa: E402
import verdicts  # noqa: E402


def merge(old: dict, proposal: dict) -> dict:
    data = copy.deepcopy(old)
    onto.upgrade(data)
    verdicts.apply(data)
    claims = {c["id"]: c for c in data["claims"]}
    seen: dict[str, str] = {}
    new_claims = []
    for row in proposal["claims"]:
        olds = [claims.get(i) for i in row["merges"]]
        if not all(olds):
            tm.fail(f"regroup: claim {row.get('id')}: unknown old claim in {row['merges']}", 2)
        for i in row["merges"]:
            if i in seen:
                tm.fail(f"regroup: the old claim {i} is in two new claims ({seen[i]}, {row['id']})", 2)
            seen[i] = row["id"]
        checks = list(dict.fromkeys(v for c in olds for v in c["checks"]))
        vs = {v["id"]: v for v in data["verifiers"]}
        if any(onto.is_tool(vs[v]) for v in checks):
            checks = [v for v in checks if onto.is_tool(vs[v])]
        code, keys = [], set()
        for c in olds:
            for ref in c.get("code", []):
                k = json.dumps(ref, sort_keys=True)
                if k not in keys:
                    keys.add(k)
                    code.append(ref)
        invs = list(dict.fromkeys(i for c in olds for i in onto.invariants_of(c)))
        merged = {"id": row["id"], "name": row["name"], "text": row["text"], "stated": all(c["stated"] for c in olds),
                  "source": "; ".join(dict.fromkeys(c["source"] for c in olds)), "layer": row.get("layer") or olds[0].get("layer", "Claims"),
                  "code": code, "plain": row["plain"], "checks": checks}
        if len(olds) > 1 or row["id"] != olds[0]["id"]:
            merged["legacy_ids"] = [c["id"] for c in olds]
            merged["parts"] = [{"id": c["id"], "text": c["text"], "stated": c["stated"], **({"invariant": c["invariant"]} if c.get("invariant") else {})}
                               for c in olds]
        if invs:
            merged["invariants"] = invs
        for key in ("cc_id", "tier_target", "waiver"):
            vals = [c[key] for c in olds if c.get(key)]
            if vals:
                merged[key] = vals[0]
        new_claims.append(merged)
    left = [c for c in claims if c not in seen]
    if left:
        tm.fail(f"regroup: the proposal leaves out the old claims {', '.join(left)}", 2)
    data["claims"] = new_claims
    promises = {p["id"]: p for p in data["promises"]}
    for p in proposal.get("promises", []):
        promises[p["id"]].update({k: v for k, v in p.items() if k != "id"})
    for p in promises.values():
        p["claims"] = [r["id"] for r in proposal["claims"] if r["promise"] == p["id"]]
    data["promises"] = [p for p in promises.values() if p["claims"]]
    for v in data["verifiers"]:
        if v["id"] in (proposal.get("check_names") or {}):
            v["name"] = proposal["check_names"][v["id"]]
    onto.sync(data)
    for e in data.get("exercises", []):
        e["claim"] = seen.get(e["claim"], e["claim"])
    verdicts.apply(data)
    return data


def regroup_explain(extra: dict, old_to_new: dict[str, str]) -> dict:
    out = copy.deepcopy(extra)
    for r in out.get("risks", []):
        r["claims"] = list(dict.fromkeys(old_to_new.get(c, c) for c in r["claims"]))
    return out


def proof(old: dict, new: dict, refs: dict | None, old_extra: dict, new_extra: dict) -> list[tuple[bool, str]]:
    rows = []
    owners: dict[str, list[str]] = {}
    for c in new["claims"]:
        for v in c["checks"]:
            owners.setdefault(v, []).append(c["id"])
    old_checks = [v["id"] for v in old["verifiers"]]
    bad = [f"{v} is under {owners.get(v, [])}" for v in old_checks if len(owners.get(v, [])) != 1]
    rows.append((not bad, f"each of the {len(old_checks)} old checks is under exactly one claim" if not bad else "a check is not under exactly one claim: " + "; ".join(bad)))
    cards = derive.claim_rows(new, new_extra)
    wrong = []
    for c in new["claims"]:
        weak, strength = onto.weakest_check(new, c)
        bug = any(verdicts.disagreeing(new, i) for i in onto.invariants_of(c))
        want = "Gap" if bug else strength
        card = cards[c["id"]]["weakest"] or {}
        if c["verdict"] != want or card.get("id") != weak["id"] or not card.get("action"):
            wrong.append(f"{c['id']}: verdict {c['verdict']}, weakest check {weak['id']} ({strength}), card names {card.get('id')}")
    rows.append((not wrong, f"each of the {len(new['claims'])} claims has the strength of its weakest check, and its card names that check with an action"
                 if not wrong else "a claim hides a weak check: " + "; ".join(wrong)))
    old_v = {c["id"]: c.get("verdict") for c in old["claims"]}
    moved = []
    for c in new["claims"]:
        for i in c.get("legacy_ids") or [c["id"]]:
            if old_v.get(i) and old_v[i] != c["verdict"]:
                moved.append(f"{i} {old_v[i]} -> {c['verdict']} ({c['name']}: {cards[c['id']]['weakest']['name']})")
    rows.append((True, "no old claim changes strength" if not moved else
                 f"{len(moved)} old claims change strength, because a claim is as strong as its weakest check: " + "; ".join(moved)))
    if refs is not None:
        before = verdict_of(old, refs, old_extra)
        after = verdict_of(new, refs, new_extra)
        same = before == after
        rows.append((same, f"the merge verdict is {after[0]} with {after[1]} blockers, as before" if same else
                     f"the merge verdict changes: {before[0]} with {before[1]} blockers before, {after[0]} with {after[1]} after; items {before[2]} -> {after[2]}"))
    return rows


def verdict_of(data: dict, refs: dict, extra: dict) -> tuple:
    d = copy.deepcopy(data)
    onto.upgrade(d)
    verdicts.apply(d)
    der = derive.derive(d, refs, extra, None)
    return der["merge"]["form"], der["merge"]["blockers"], [i["label"] for i in der["merge"]["items"]]


def table(new: dict) -> str:
    """The plain table: promise -> claim name -> old ids, with the strength and the weakest check."""
    cards = derive.claim_rows(new)
    out = ["| Promise | Claim | Old claims | Strength | Weakest check |", "|---|---|---|---|---|"]
    for p in new["promises"]:
        for cid in p["claims"]:
            c = next(x for x in new["claims"] if x["id"] == cid)
            w = cards[cid]["weakest"]
            out.append(f"| {p.get('name') or p['label']} | {c['name']} | {', '.join(c.get('legacy_ids') or [c['id']])} | {c['verdict']} | "
                       f"{w['name']}: {w['text'].split('. ', 1)[-1] if w['result'] != 'none' else w['text']} |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", required=True)
    ap.add_argument("--proposal", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--explain")
    ap.add_argument("--explain-out")
    ap.add_argument("--refs", help="refs.resolved.json of the map head: the merge verdict before and after")
    ap.add_argument("--table", action="store_true", help="print the plain table")
    args = ap.parse_args()
    if Path(args.out).resolve() == Path(args.map).resolve():
        tm.fail("regroup: --out must not be the input map; write a copy", 2)
    old = tm.load(args.map)
    proposal = tm.load(args.proposal)
    new = merge(old, proposal)
    errors = tm.validate(new)
    if errors:
        print("\n".join(errors))
        print(f"INVALID: {len(errors)} errors")
        return 1
    tm.save(new, args.out)
    old_extra = tm.load(args.explain) if args.explain else {}
    old_to_new = {i: c["id"] for c in new["claims"] for i in (c.get("legacy_ids") or [c["id"]])}
    new_extra = regroup_explain(old_extra, old_to_new)
    if args.explain_out:
        tm.save(new_extra, args.explain_out)
    refs = tm.load(args.refs) if args.refs else None
    ok = True
    for good, line in proof(old, new, refs, old_extra, new_extra):
        ok &= good
        print(("PASS " if good else "FAIL ") + line)
    print("summary: " + ", ".join(f"{k} {v}" for k, v in new["summary"].items()) + f" ({len(new['claims'])} claims, {len(new['verifiers'])} checks)")
    for line in onto.group_lint(new):
        print(line)
    for kind, item, why in onto.name_problems(new):
        print(f"name: the {kind} {item}: {why}")
    if args.table:
        print(table(new))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
