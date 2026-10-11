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


def split_checks(data: dict, splits: dict) -> dict[str, list[str]]:
    """One check for each formal property: replace a check that proves many properties with one
    check per property, each with its own controls, under the old claim (`part`) that states it.
    Returns {old check id: new check ids}."""
    out = {}
    for vid, rows in (splits or {}).items():
        v = next((x for x in data["verifiers"] if x["id"] == vid), None)
        if not v:
            tm.fail(f"regroup: split_checks names {vid}, which the map does not have", 2)
        mine = [k for k in data["controls"] if k["verifier"] == vid]
        given = [k for r in rows for k in r.get("controls", [])]
        if sorted(given) != sorted(set(given)) or not set(given) <= {k["id"] for k in mine}:
            tm.fail(f"regroup: the split of {vid} gives a control twice, or a control of another check", 2)
        new = []
        for r in rows:
            n = copy.deepcopy(v)
            n.update({"id": r["id"], "name": r["name"], "property": r["property"]})
            if n.get("formal_record"):
                n["formal_record"] = {**n["formal_record"], "formal": {"verdict": r.get("formal_verdict", "Formal"), "missing": r.get("missing", [])}}
            n["claims"] = [r["part"]]
            new.append(n)
            for k in mine:
                if k["id"] in r.get("controls", []):
                    k["verifier"] = r["id"]
        left = [k["id"] for k in mine if k["verifier"] == vid]
        if left:
            tm.fail(f"regroup: the split of {vid} leaves its controls {left} with no check", 2)
        i = data["verifiers"].index(v)
        data["verifiers"][i:i + 1] = new
        for c in data["claims"]:
            if vid in c.get("checks", []):
                c["checks"] = [x for y in c["checks"] for x in ([r["id"] for r in rows if r["part"] == c["id"]] if y == vid else [y])]
        out[vid] = [r["id"] for r in rows]
    return out


def merge(old: dict, proposal: dict) -> dict:
    data = copy.deepcopy(old)
    onto.upgrade(data)
    verdicts.apply(data)
    data["_splits"] = split_checks(data, proposal.get("split_checks"))
    # New controls, for example a planted-wrong spec for a property that had none (recorded runs).
    have = {k["id"] for k in data["controls"]}
    for k in proposal.get("new_controls") or []:
        if k["id"] in have or not any(v["id"] == k["verifier"] for v in data["verifiers"]):
            tm.fail(f"regroup: new control {k['id']}: its id exists, or its check {k['verifier']} does not", 2)
        data["controls"].append(k)
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
            # A none check goes, unless it is the only evidence of an old claim (a part).
            alone = {v for c in olds for v in c["checks"] if not any(onto.is_tool(vs[x]) for x in c["checks"] if x in vs)}
            checks = [v for v in checks if onto.is_tool(vs[v]) or v in alone]
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
            merged["parts"] = [{"id": c["id"], "text": c["text"], "stated": c["stated"], "checks": list(c["checks"]),
                                **({"invariant": c["invariant"]} if c.get("invariant") else {})} for c in olds]
        if invs:
            merged["invariants"] = invs
        # A merge keeps the risk of its parts: a risky old claim makes the new claim risky.
        if len(olds) > 1 or row.get("text") != olds[0].get("text"):
            merged["risk"] = row.get("risk", any(onto.risky(c) for c in olds))
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
        v.update((proposal.get("check_fields") or {}).get(v["id"]) or {})
    listed = {v for c in data["claims"] for v in c["checks"]}
    data["verifiers"] = [v for v in data["verifiers"] if onto.is_tool(v) or v["id"] in listed]
    onto.sync(data)
    for e in data.get("exercises", []):
        e["claim"] = seen.get(e["claim"], e["claim"])
    splits = data.pop("_splits")
    onto.upgrade(data)
    verdicts.apply(data)
    data["_splits"] = splits
    return data


def regroup_explain(extra: dict, old_to_new: dict[str, str]) -> dict:
    out = copy.deepcopy(extra)
    for r in out.get("risks", []):
        r["claims"] = list(dict.fromkeys(old_to_new.get(c, c) for c in r["claims"]))
    return out


def proof(old: dict, new: dict, refs: dict | None, old_extra: dict, new_extra: dict, splits: dict | None = None) -> list[tuple[bool, str]]:
    rows = []
    owners: dict[str, list[str]] = {}
    for c in new["claims"]:
        for v in c["checks"]:
            owners.setdefault(v, []).append(c["id"])
    splits = splits or {}
    old_checks = [x for v in old["verifiers"] if onto.is_tool(v) for x in splits.get(v["id"], [v["id"]])]
    bad = [f"{v} is under {owners.get(v, [])}" for v in old_checks if len(owners.get(v, [])) != 1]
    lost = sorted({k["id"] for k in old["controls"]} - {k["id"] for k in new["controls"]})
    split_text = "; ".join(f"{a} is now {len(b)} checks, one for each property" for a, b in splits.items())
    rows.append((not bad and not lost, (f"each of the {len([v for v in old['verifiers'] if onto.is_tool(v)])} old tool checks is under exactly one claim"
                                        + (f" ({split_text})" if split_text else "") + ", and each old control is kept"
                                        + (f"; {len(new['controls']) - len(old['controls'])} new controls" if len(new['controls']) > len(old['controls']) else "")) if not bad and not lost else
                 "a check is not under exactly one claim, or a control is lost: " + "; ".join(bad + lost)))
    cards = derive.claim_rows(new, new_extra)
    wrong = []
    for c in new["claims"]:
        parts = onto.parts_of(new, c)
        weakest = max((onto.part_strength(new, p)[0] for p in parts), key=onto.VERDICTS.index)
        weak = onto.claim_strength(new, c)[2]
        card = cards[c["id"]]["weakest"] or {}
        flagged = {v["id"] for v in onto.flagged(new, c)}
        shown = set((cards[c["id"]]["flagged"] or {}).get("checks", []))
        if c["verdict"] != weakest or card.get("id") != (weak or {}).get("id") or not card.get("action") or flagged != shown:
            wrong.append(f"{c['id']}: verdict {c['verdict']}, weakest part {weakest}, card names {card.get('id')}, flagged {sorted(flagged)} shown {sorted(shown)}")
    rows.append((not wrong, f"each of the {len(new['claims'])} claims has the strength of its weakest part, its card names that part's evidence with an action, "
                 "and each weak check is flagged on its card" if not wrong else "a claim hides a weak part or a weak check: " + "; ".join(wrong)))
    old_v = {c["id"]: c.get("verdict") for c in old["claims"]}
    moved = []
    for c in new["claims"]:
        for p in onto.parts_of(new, c):
            for i in [p["id"]] if c.get("parts") else (c.get("legacy_ids") or [c["id"]]):
                st, best = onto.part_strength(new, p)
                if old_v.get(i) and old_v[i] != st:
                    moved.append(f"{i} {old_v[i]} -> {st} (a part of {c['name']}; its strongest check is {derive.check_name(new, best) if best else 'none'})")
    rows.append((True, "no old claim changes strength as a part" if not moved else
                 f"{len(moved)} old claims change strength as a part of their new claim: " + "; ".join(moved)))
    for c in new["claims"]:
        if c.get("parts") and len(c["parts"]) > 1 and c["verdict"] != max((old_v.get(p["id"]) for p in c["parts"] if old_v.get(p["id"])), key=onto.VERDICTS.index, default=c["verdict"]):
            rows.append((True, f"{c['name']} is {c['verdict']}: its weakest part sets it"))
    if refs is not None:
        stored = (refs.get("derived") or {}).get("merge") or {}
        before = verdict_of(old, refs, old_extra)
        after = verdict_of(new, refs, new_extra)
        to_new = {i: c["id"] for c in new["claims"] for i in (c.get("legacy_ids") or [c["id"]])}
        key = lambda items, m: ({i["label"] for i in items if not i["href"].startswith("#claim-")},  # noqa: E731
                                {m.get(h, h) for h in (i["href"][7:].upper() for i in items if i["href"].startswith("#claim-"))})
        same = key(before[2], to_new) == key(after[2], {})
        prom = sorted(key(after[2], {})[0])
        rows.append((same, f"the merge verdict is {after[0]} with {after[1]} blockers. The stored page (the old rules) had {stored.get('blockers')} blockers. "
                     f"The same {len(prom)} promise blockers stay; the rest are risky claims below their evidence bar, a new rule. "
                     f"Under the new rules the old map has {before[1]} blockers, and each of them maps to a blocker of the new map" if same else
                     f"the merge verdict changes: {before[0]} with {before[1]} blockers under the new rules before, {after[0]} with {after[1]} after; "
                     f"items {[i['label'] for i in before[2]]} -> {[i['label'] for i in after[2]]}"))
    return rows


def verdict_of(data: dict, refs: dict, extra: dict) -> tuple:
    d = copy.deepcopy(data)
    onto.upgrade(d)
    verdicts.apply(d)
    der = derive.derive(d, refs, extra, None)
    return der["merge"]["form"], der["merge"]["blockers"], [i for i in der["merge"]["items"] if der["merge"]["form"] == "not-ready"]


def table(new: dict, extra: dict | None = None) -> str:
    """The plain table: promise -> claim name -> old ids, with the strength and the weakest check."""
    cards = derive.claim_rows(new, extra)
    word = {"caught": "caught its bug", "missed": "missed its bug", "cannot-fail": "cannot fail", "no-bug": "no planted bug",
            "recorded": "a record, not run again", "checked": "a mechanical check, no planted bug", "broken": "fails at the head",
            "none": "no tool check"}
    out = ["| Promise | Claim | Old claims | Surface | Bar | Met | Strength | Weakest part's evidence, or a flagged check |",
           "|---|---|---|---|---|---|---|---|"]
    for p in new["promises"]:
        for cid in p["claims"]:
            c = next(x for x in new["claims"] if x["id"] == cid)
            row = cards[cid]
            w, b, f = row["weakest"], row["bar"], row["flagged"]
            part = f" ({w['part']})" if w.get("part") else ""
            ev = f"{w['name']}{part}: {word[w['result']]}" + (f". Flagged: {f['text']}" if f else "")
            met = "met" if b["met"] else ("below: " + b["why"]) + (" (blocks)" if b["risky"] else "")
            out.append(f"| {p.get('name') or p['label']} | {c['name']} | {', '.join(c.get('legacy_ids') or [c['id']])} | {b['surface']}"
                       f"{' (mixed)' if b['mixed'] else ''} | {b['need']} | {met} | {c['verdict']} | {ev} |")
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
    splits = new.pop("_splits")
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
    for good, line in proof(old, new, refs, old_extra, new_extra, splits):
        ok &= good
        print(("PASS " if good else "FAIL ") + line)
    print("summary: " + ", ".join(f"{k} {v}" for k, v in new["summary"].items()) + f" ({len(new['claims'])} claims, {len(new['verifiers'])} checks)")
    for line in onto.group_lint(new):
        print(line)
    for kind, item, why in onto.name_problems(new):
        print(f"name: the {kind} {item}: {why}")
    if args.table:
        print(table(new, new_extra))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
