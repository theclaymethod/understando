"""understando formalize --sidecar FILE: bring a formal sidecar into the evidence store, both ways.
understando formalize --recheck RECORD: run a record's check, conformance run and controls again.

Sync:
1. Proposed claims. Each proposed claim of the sidecar (FC1, ...) maps to a claim or a part of the
   store by a stable key, never by its text: the `claim` that an earlier sync wrote into the
   sidecar, else the claim or part whose `formal_key` is the key. Only a key with no claim becomes
   a new claim. Sync writes the key on both sides.
2. Each record takes the user's decisions from the store: when each invariant item of the record
   is author user and accepted, `invariant` becomes {author: user, ref, status: confirmed}. Then
   formal_record.rate() rates the record again. An agent-picked invariant is never Formal.
3. Checks. A record with `properties` (one for each TLA+ invariant or property, or Lean theorem
   group) becomes one check for each property, each with its own controls and the claim of its
   part. Else the record is one check with the record ID.
4. IDs and names stay. A check keeps its ID, its name and its claim links on each sync. A control
   of the record keeps its ID; when a control of another check holds that ID, the control gets a
   fresh ID, and the sidecar records it (`map_id`).
5. Sync is idempotent: a second run with the same sidecar gives the same store.

Recheck: the record's helper calls (each result keeps its `rerun`) run again in the repo, with
the stamp-time repo path replaced by the repo of this run. Then the drift block is stamped again
at the repo HEAD, the record is rated again, the sidecar is written, and sync runs.
"""

from __future__ import annotations

import copy
import json
import re
import string
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import coderef  # noqa: E402
import formal_record  # noqa: E402
import store  # noqa: E402
from run_control import tail  # noqa: E402

KEEP = ("ladder_tier", "conformance", "route", "invariant", "witness", "drift", "formal", "blocker_open", "card", "witness_test")
OWNED = ("kind", "ladder", "description", "recorded", "formal_record", "formal", "property", "feature")
HERE = Path(__file__).resolve().parent


class Refused(Exception):
    pass


def holders(data: dict) -> dict[str, tuple[dict, dict | None]]:
    """Each claim ID and part ID of the store: (the claim, the part or None)."""
    out: dict[str, tuple[dict, dict | None]] = {}
    for c in data["claims"]:
        out.setdefault(c["id"], (c, None))
        for p in c.get("parts", []):
            out.setdefault(p["id"], (c, p))
    return out


def resolve_proposed(data: dict, side: dict, report: list[str]) -> dict[str, str]:
    idmap: dict[str, str] = {}
    hold = holders(data)
    keyed = {}
    for c in data["claims"]:
        if c.get("formal_key"):
            keyed.setdefault(c["formal_key"], c["id"])
        for p in c.get("parts", []):
            if p.get("formal_key"):
                keyed.setdefault(p["formal_key"], p["id"])
    for pc in side.get("proposed_claims", []):
        key = pc["id"]
        target = (pc.get("claim") if pc.get("claim") in hold else None) or keyed.get(key)
        if not target:
            target = store.next_id(data, "claims")
            data["claims"].append({"id": target, "text": pc["text"], "checks": [], "formal_key": key,
                                   **({"feature": pc["feature"]} if pc.get("feature") else {})})
            hold = holders(data)
            report.append(f"new claim {target} for the proposed claim {key}")
        claim, part = hold[target]
        (part if part is not None else claim)["formal_key"] = key
        pc["claim"] = target
        idmap[key] = target
    return idmap


def judge(rec: dict, ids: list[str], data: dict) -> tuple[dict, dict]:
    """The invariant block and the rating of a record (or of one property of it)."""
    import strength
    inv = dict(rec.get("invariant") or {})
    if strength.intent(data, ids)[0]:
        inv.update(author="user", ref="store invariants " + ", ".join(ids), status="confirmed")
    elif ids or inv.get("author") != "user":
        inv.update(author="agent", ref=None, status="proposed")
    return inv, formal_record.rate({**rec, "invariant": inv})


def taken(data: dict) -> set[str]:
    return {x["id"] for s in ("claims", "checks", "controls", "invariants") for x in data.get(s, [])}


def fresh_id(data: dict, base: str, also: set[str]) -> str:
    """A new ID near `base`: K2a -> K2b (the next free letter), else base-2, base-3, ..."""
    used = taken(data) | also
    stem = base[:-1] if re.search(r"\d[a-z]$", base) else base
    for ch in string.ascii_lowercase:
        if f"{stem}{ch}" not in used:
            return f"{stem}{ch}"
    n = 2
    while f"{base}-{n}" in used:
        n += 1
    return f"{base}-{n}"


def store_control(rec: dict, k: dict, vid: str, models: list[str], before: dict | None = None) -> dict:
    r = k["result"]
    ctl = r.get("control") or {}
    where = ctl.get("file") or (models[0] if models else "model")
    edits = r.get("edits") or ([{**ctl["edit"], "path": where}] if ctl.get("edit") else [])
    edits = [e for e in edits if e.get("find") or e.get("op") in coderef.ANCHOR_OPS] or \
        [{"op": "append", "path": models[0] if models else "model", "text": "(recorded control)"}]
    red = r.get("status") == "red"
    return {"id": k["map_id"], "check": vid, "kind": "planted", "sidecar": rec["id"],
            "description": f"A planted {'wrong model' if k['target'] == 'model' else 'wrong function'} from formalize.",
            "edits": edits, "expect": {"status": "red"},
            "result": {"status": "red" if red else ("green" if r.get("status") == "green" else "error"), "exit": r.get("exit"),
                       "matched": True if red else None, "recorded": True,
                       "output_tail": re.sub(r"/Users/[^/\s]+", "~", tail(r.get("output_tail"), 12)),
                       "ran_at": r.get("ran_at") or ((before or {}).get("result") or {}).get("ran_at") or store.now()}}


def base_check(rec: dict, side_path: Path, models: list[str], feature: str | None) -> dict:
    conf = (rec.get("conformance") or {}).get("result") or {}
    v = {"kind": rec["kind"] if rec["kind"] in ("lean", "tla") else "property", "ladder": rec["ladder_tier"],
         "description": rec["description"],
         "recorded": {"source": f"formal sidecar {side_path.name}, record {rec['id']}",
                      "result": f"check {(rec.get('check') or {}).get('status')}; conformance {conf.get('status')}"},
         "formal_record": {**{k: copy.deepcopy(rec[k]) for k in KEEP if k in rec}, "sidecar": str(side_path)},
         **({"feature": feature} if feature else {})}
    if rec["ladder_tier"] >= store.FORMAL_RUNG:
        v["formal"] = {"tool": "lean" if rec["kind"] == "lean" else "tla", "artifact": models[0] if models else "unknown",
                       "conformance": {"status": "pass" if conf.get("status") == "green" else "fail",
                                       "source": " ".join(conf.get("argv") or []) or "the conformance run of the record"}}
    return v


def put_check(data: dict, v: dict, target: str | None) -> None:
    i = next((n for n, x in enumerate(data["checks"]) if x["id"] == v["id"]), None)
    if i is None:
        data["checks"].append(v)
    else:
        data["checks"][i] = v
    if not target:
        return
    claim, part = holders(data)[target]
    if v["id"] not in claim["checks"]:
        claim["checks"].append(v["id"])
    if part is not None and v["id"] not in part["checks"]:
        part["checks"].append(v["id"])


def add_record(data: dict, rec: dict, idmap: dict[str, str], side_path: Path, report: list[str], used: set[str]) -> list[str]:
    ids = [it["id"] for it in (rec.get("invariant") or {}).get("items", [])]
    targets = [idmap.get(x, x) for x in rec.get("claims", [])]
    hold = holders(data)
    ids = ids or sorted({i for t in targets if t in hold for i in (hold[t][1] or hold[t][0]).get("invariants", [])})
    inv, rated = judge(rec, ids, data)
    rec["invariant"], rec["formal"] = inv, rated
    models = [m["path"] for m in (rec.get("drift") or {}).get("model_files", [])]
    props = rec.get("properties") or []
    for p in props:
        p.setdefault("controls", [])
        if not p.get("check"):
            p["check"] = fresh_id(data, f"{rec['id']}a", used | {q["check"] for q in props if q.get("check")})
    mine = {rec["id"]} | {p["check"] for p in props}
    by_id = {k["id"]: k for k in data["controls"]}
    for k in rec.get("controls", []):
        mid = k.get("map_id") or k["id"]
        other = by_id.get(mid)
        if mid in used or (other and other["check"] not in mine and other.get("sidecar") != rec["id"]):
            mid = fresh_id(data, k["id"], used)
            report.append(f"{rec['id']}: the control {k['id']} is {mid} in the store, because another check holds {k['id']}")
        k["map_id"] = mid
        used.add(mid)
    owner = {}
    for p in props:
        for kid in p["controls"]:
            owner[kid] = p
    for k in rec.get("controls", []):
        p = owner.get(k["id"]) or next((x for x in props if x["name"] == (k.get("property") or (k["result"].get("control") or {}).get("name"))), None)
        if props and not p:
            raise Refused(f"the record {rec['id']} has a control {k['id']} that names no property; its properties are "
                          f"{', '.join(x['name'] for x in props)}. Build the record again with --control ...:PROPERTY.")
        if p:
            owner[k["id"]] = p
            if k["id"] not in p["controls"]:
                p["controls"].append(k["id"])
    feature = next((hold[t][0].get("feature") for t in targets if t in hold), None)
    base = base_check(rec, side_path, models, feature)
    old = {v["id"]: v for v in data["checks"] if v["id"] in mine or (v.get("formal_record") or {}).get("sidecar") and
           (v.get("recorded") or {}).get("source", "").endswith(f"record {rec['id']}")}
    out = []
    groups = [(p["check"], [idmap.get(p["part"], p["part"])], [k for k in rec.get("controls", []) if owner.get(k["id"]) is p], p)
              for p in props] or [(rec["id"], targets, rec.get("controls", []), None)]
    for vid, tgts, ctls, p in groups:
        v = {k: x for k, x in (old.get(vid) or {}).items() if k not in OWNED}
        v.update(copy.deepcopy(base))
        v["id"] = vid
        sub_rec = {**rec, "controls": ctls} if p else rec
        _, prated = judge(sub_rec, ids, data)
        v["formal_record"]["formal"] = prated
        v["formal_record"]["controls"] = [{"id": k["map_id"], "target": k["target"], "status": k["result"].get("status")} for k in ctls]
        v["recorded"]["result"] += f"; record verdict {prated['verdict']}"
        if p:
            v["property"] = p["name"]
            v.setdefault("name", p.get("check_name") or p["name"])
        v.setdefault("name", rec["description"][:60])
        for t in tgts:
            if t not in holders(data):
                raise Refused(f"the record {rec['id']} names the claim or part {t}, and the store has no such claim")
        put_check(data, v, tgts[0] if tgts else None)
        for t in tgts[1:]:
            put_check(data, v, t)
        out.append(vid)
    gone = set(old) - set(out)
    if gone:
        data["checks"] = [x for x in data["checks"] if x["id"] not in gone]
        report.append(f"{rec['id']}: {', '.join(sorted(gone))} replaced by {', '.join(out)}")
    rec_mids = {k["map_id"] for k in rec.get("controls", [])}
    befores = {k["id"]: k for k in data["controls"] if k["id"] in rec_mids}
    data["controls"] = [k for k in data["controls"] if k["id"] not in rec_mids and k.get("sidecar") != rec["id"] and k["check"] not in gone]
    for k in rec.get("controls", []):
        data["controls"].append(store_control(rec, k, owner[k["id"]]["check"] if props else rec["id"], models, befores.get(k["map_id"])))
    report.append(f"{rec['id']}: {rated['verdict']}" + (f" ({'; '.join(rated['missing'])})" if rated["missing"] else "")
                  + (f"; {len(out)} checks, one for each property" if props else ""))
    return out


def sync(c: store.Ctx, path: str) -> dict:
    data = c.need_data()
    before = json.dumps(data, sort_keys=True)
    side_path = Path(path).resolve()
    side = json.loads(side_path.read_text(encoding="utf-8"))
    report: list[str] = []
    checks: list[str] = []
    try:
        idmap = resolve_proposed(data, side, report)
        used: set[str] = set()
        for rec in side.get("verifiers", []):
            checks += add_record(data, rec, idmap, side_path, report, used)
    except Refused as exc:
        store.fail(f"formalize --sidecar: refuse: {exc}", 1)
    ids = {v["id"] for v in data["checks"]}
    for cl in data["claims"]:
        cl["checks"] = [x for x in cl["checks"] if x in ids]
        for p in cl.get("parts", []):
            p["checks"] = [x for x in p["checks"] if x in ids]
    side_path.write_text(json.dumps(side, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    import strength
    strength.apply(data)
    changed = before != json.dumps(data, sort_keys=True)
    c.save(data)
    return {"report": report, "claims": idmap, "checks": checks, "changed": changed}


# ---- recheck -----------------------------------------------------------------------------------

def rerun(result: dict, old_root: str | None, new_root: Path) -> dict:
    """Run a helper call again. The stamp-time repo path becomes the repo of this run."""
    call = result.get("rerun")
    if not call:
        raise Refused("the result has no `rerun` call (it is older than recheck); run the helper again by hand")
    swap = (lambda x: x.replace(old_root, str(new_root))) if old_root else (lambda x: x)
    argv = [sys.executable, str(HERE / call["script"]), *[swap(a) for a in call["args"]]]
    cwd = swap(call.get("cwd") or str(new_root))
    out = subprocess.run(argv, cwd=cwd if Path(cwd).is_dir() else str(new_root), capture_output=True, text=True, timeout=3600)
    try:
        return formal_record.trim(json.loads(out.stdout))
    except json.JSONDecodeError:
        return {"status": "error", "exit": out.returncode, "output_tail": tail(out.stdout + out.stderr, 12), "rerun": call}


def commands(rec: dict) -> list[list[str]]:
    rows = [rec.get("check") or {}, (rec.get("conformance") or {}).get("result") or {}] + [k["result"] for k in rec.get("controls", [])]
    return [[call["script"], *call["args"]] for call in (r.get("rerun") for r in rows) if call]


def recheck(c: store.Ctx, rid: str, sidecar: str | None) -> int:
    repo = c.need_repo()
    side_path = Path(sidecar).resolve() if sidecar else c.run / "formal" / "verifiers.json"
    if not side_path.is_file():
        store.fail(f"formalize --recheck: no sidecar at {side_path}", 2)
    side = json.loads(side_path.read_text(encoding="utf-8"))
    rec = next((r for r in side.get("verifiers", []) if r["id"] == rid), None)
    if not rec:
        store.fail(f"formalize --recheck: the sidecar has no record {rid}", 2)
    if not store.confirm(c, f"formalize --recheck {rid}", commands(rec), str(repo)):
        return 0
    old_root = (rec.get("drift") or {}).get("root")
    lines = []
    try:
        rec["check"] = rerun(rec.get("check") or {}, old_root, repo)
        lines.append(f"check: {rec['check'].get('status')}")
        conf = rec.setdefault("conformance", {})
        conf["result"] = rerun(conf.get("result") or {}, old_root, repo)
        lines.append(f"conformance: {conf['result'].get('status')}")
        for k in rec.get("controls", []):
            k["result"] = rerun(k["result"], old_root, repo)
            lines.append(f"control {k['id']} ({k['target']}): {k['result'].get('status')}")
    except Refused as exc:
        store.fail(f"formalize --recheck: refuse: {exc}", 1)
    d = rec.get("drift") or {}
    rec["drift"] = formal_record.stamp_of(repo, [f["path"] for f in d.get("code_files", [])], [f["path"] for f in d.get("model_files", [])])
    rec["formal"] = formal_record.rate(rec)
    rec["rechecked_at"] = store.now()
    side_path.write_text(json.dumps(side, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines.append(f"{rid}: {rec['formal']['verdict']} at {rec['drift']['commit'][:10]}" + (f" ({'; '.join(rec['formal']['missing'])})" if rec["formal"]["missing"] else ""))
    if c.store and c.store.is_file():
        out = sync(c, str(side_path))
        lines += out["report"]
    store.emit(c, {"record": rid, "formal": rec["formal"], "lines": lines}, "\n".join(lines))
    return 0 if rec["formal"]["verdict"] == "Formal" else 1
