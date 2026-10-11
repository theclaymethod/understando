"""understando formalize --sidecar FILE: bring a formal sidecar into the trust map, both ways.

1. Each proposed claim of the sidecar that the map does not hold becomes a claim (stated: false,
   source "... (formal FC1)"). The agent then writes its plain text and its promise.
2. Each record takes the user's decisions from the map: when every invariant item of the record
   is author user and accepted, with no possible bug, `invariant` becomes {author: user, ref:
   the journal rows, status: confirmed}. Then formal_record.rate() rates the record again. A
   record whose only gap is a confirmed invariant that the code disagrees with stays
   "Formal (pending)" until the fix lands and the check runs again against the user's wording.
3. Each record becomes a trust-map verifier with the same id: kind, ladder, a `formal` block
   (tool, artifact, conformance link), recorded evidence, `formal_record` (the sidecar fields),
   and its controls with their recorded results. The record's verdict gates the claim: only
   "Formal" lets the verifier prove a claim at rung 4 or 5.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import coderef  # noqa: E402
import ctx as context  # noqa: E402
import formal_record  # noqa: E402
import journal  # noqa: E402
import ops  # noqa: E402
import tm  # noqa: E402
import verdicts  # noqa: E402

KEEP = ("ladder_tier", "conformance", "route", "invariant", "witness", "drift", "formal", "blocker_open", "card", "witness_test")


def tail(text: str | None, n: int = 12) -> str:
    return "\n".join((text or "").splitlines()[-n:])


def sync(c: context.Ctx, path: str) -> dict:
    data = c.need_map()
    side_path = Path(path).resolve()
    side = json.loads(side_path.read_text(encoding="utf-8"))
    rows = journal.read(c.journal)
    invs = {i["id"]: i for i in data.get("invariants", [])}
    report = []

    idmap: dict[str, str] = {}
    for pc in side.get("proposed_claims", []):
        tag = f"(formal {pc['id']})"
        found = next((x for x in data["claims"] if x["source"].endswith(tag) or x["text"] == pc["text"]), None)
        if found:
            idmap[pc["id"]] = found["id"]
            continue
        cid = ops.next_id(data, "C")
        data["claims"].append({"id": cid, "cc_id": None, "text": pc["text"], "stated": False,
                               "source": f"{pc['source']} {tag}", "layer": "Formal pilot",
                               "plain": {"what": pc["text"], "proof": "A formal record checks it."}})
        idmap[pc["id"]] = cid
        report.append(f"claim {cid} from {pc['id']}: {pc['text']}")

    for rec in side.get("verifiers", []):
        items = (rec.get("invariant") or {}).get("items", [])
        ids = [it["id"] for it in items]
        confirmed = [i for i in ids if invs.get(i, {}).get("author") == "user" and invs[i].get("status") == "accepted"]
        for i in confirmed:
            if invs[i].get("possible_bug"):
                fixed = fix_landed(c, data, rec, invs[i])
                if fixed:
                    invs[i]["possible_bug_fixed"] = {**fixed, "bugs": invs[i].pop("possible_bug")}
                    report.append(f"{i}: the possible bug is fixed at {fixed['commit'][:10]} ({fixed['why']})")
        bugs = [i for i in confirmed if invs[i].get("possible_bug")]
        if ids and len(confirmed) == len(ids) and not bugs:
            refs = [f"journal {r['ts']}" for r in rows if r.get("kind") == "invariant" and r.get("author") == "user" and r.get("invariant") in ids]
            rec["invariant"].update(author="user", ref="; ".join(refs) or "trust-map invariants " + ", ".join(ids), status="confirmed")
        else:
            rec["invariant"].update(author="agent", ref=None, status="proposed")
        if bugs:
            route = invs[bugs[0]].get("route")
            if route:
                rec["route"] = route
                rec["route_reason"] = (f"The user confirmed {bugs[0]}, and the code at the head does not obey it: "
                                       f"{invs[bugs[0]]['possible_bug'][0].get('where', 'see the invariant')}.")
        rated = formal_record.rate(rec)
        if bugs and rated["verdict"].startswith("Formal"):
            fix = invs[bugs[0]].get("fix_branch", "the fix branch")
            rated = {"verdict": "Formal (pending)",
                     "missing": [f"{i}: the code disagrees with the confirmed invariant; fix pending on {fix}, then run the check again against the user's {i}"
                                 for i in bugs] + [f"{i}: not confirmed by the user" for i in ids if i not in confirmed]}
        rec["formal"] = rated
        report.append(f"{rec['id']}: {rated['verdict']}" + (f" ({'; '.join(rated['missing'])})" if rated["missing"] else ""))
        add_verifier(data, rec, idmap, side_path)

    side_path.write_text(json.dumps(side, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    import onto
    onto.reconcile(data)  # shape 2: each new claim lists its checks
    verdicts.apply(data)
    errors = tm.validate(data, promises=False)
    if errors:
        tm.fail("formalize --sidecar: the map is invalid:\n" + "\n".join(errors), 1)
    tm.save(data, c.map)
    return {"report": report, "claims": idmap}


def fix_landed(c: context.Ctx, data: dict, rec: dict, inv: dict) -> dict | None:
    """A possible bug of a confirmed invariant is fixed when the record was checked again at a
    commit whose code differs from the commit that showed the bug, the model check and the
    conformance run are green there, and no blocker is open. Else None."""
    drift = rec.get("drift") or {}
    commit = drift.get("commit")
    seen_at = next((b.get("at_commit") for b in inv.get("possible_bug", []) if b.get("at_commit")), None) or data["head"]
    if not (c.repo and commit) or commit == seen_at or rec.get("blocker_open"):
        return None
    if (rec.get("check") or {}).get("status") != "green" or ((rec.get("conformance") or {}).get("result") or {}).get("status") != "green":
        return None
    changed = []
    for f in drift.get("code_files", []):
        before = subprocess.run(["git", "-C", str(c.repo), "rev-parse", f"{seen_at}:{f['path']}"], capture_output=True, text=True).stdout.strip()
        if before and before != f.get("blob"):
            changed.append(f["path"])
    if not changed:
        return None
    return {"commit": commit, "record": rec["id"], "at": tm.now(),
            "why": f"record {rec['id']} is green at {commit[:10]}, and {', '.join(changed)} changed after {seen_at[:10]}"}


def add_verifier(data: dict, rec: dict, idmap: dict[str, str], side_path: Path) -> None:
    claims = [idmap.get(x, x) for x in rec.get("claims", [])]
    claims = [x for x in claims if any(c["id"] == x for c in data["claims"])]
    models = [m["path"] for m in (rec.get("drift") or {}).get("model_files", [])]
    conf = rec.get("conformance") or {}
    status = "pass" if (conf.get("result") or {}).get("status") == "green" else "fail"
    argv = " ".join((conf.get("result") or {}).get("argv", []))
    v = {"id": rec["id"], "kind": "lean" if rec["kind"] == "lean" else ("tla" if rec["kind"] == "tla" else "property"),
         "ladder": rec["ladder_tier"], "claims": claims, "tier": "fact", "description": rec["description"],
         "recorded": {"source": f"formal sidecar {side_path.name}, record {rec['id']}",
                      "result": f"check {(rec.get('check') or {}).get('status')}; conformance {(conf.get('result') or {}).get('status')}; record verdict {rec['formal']['verdict']}"},
         "independence": rec.get("independence") or {"by": "tool", "tool": rec["kind"]},
         "cost": rec.get("cost") or {"usd": 0}, "provenance": f"understando formalize; the record is in {side_path}.",
         "formal_record": {**{k: rec[k] for k in KEEP if k in rec},
                           "controls": [{"id": k["id"], "target": k["target"], "status": k["result"].get("status")} for k in rec.get("controls", [])],
                           "sidecar": str(side_path)}}
    if v["independence"].get("by") != "tool":
        v["independence"] = {"by": "tool", "tool": rec["kind"]}
    if rec["ladder_tier"] >= 4:
        v["formal"] = {"tool": "lean" if rec["kind"] == "lean" else "tla", "artifact": models[0] if models else "unknown",
                       "conformance": {"status": status, "source": argv or "the conformance run of the record"}}
    data["verifiers"] = [x for x in data["verifiers"] if x["id"] != v["id"]] + [v]
    data["controls"] = [k for k in data["controls"] if k["verifier"] != v["id"]]
    for k in rec.get("controls", []):
        r = k["result"]
        ctl = r.get("control") or {}
        where = ctl.get("file") or (models[0] if models else "model")
        if r.get("edits"):
            edits = r["edits"]
        elif ctl.get("edit"):
            edits = [{**ctl["edit"], "path": where}]
        else:  # a record from before anchor controls: the typed find and replace
            edits = [{"op": "replace", "path": where, "find": ctl.get("find", ""), "replace": ctl.get("replace", "")}]
        edits = [e for e in edits if e.get("find") or e["op"] in coderef.ANCHOR_OPS] or [{"op": "append", "path": models[0] if models else "model", "text": "(recorded control)"}]
        red = r.get("status") == "red"
        data["controls"].append({
            "id": k["id"], "verifier": v["id"], "recipe": "plant-violation",
            "description": f"A planted {'wrong model' if k['target'] == 'model' else 'wrong function'} from the formal pilot.",
            "edits": edits, "expect": {"status": "red"},
            "result": {"status": "red" if red else ("green" if r.get("status") == "green" else "error"), "exit": r.get("exit"),
                       "matched": True if red else None, "recorded": True,
                       "output_tail": re.sub(r"/Users/[^/\s]+", "~", tail(r.get("output_tail"))), "ran_at": tm.now()}})
