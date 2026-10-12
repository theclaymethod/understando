"""understando maintain: keep the verify skill and its verifiers honest as the app changes.

    understando maintain [--feature F] [--at REF] [--yes]

The pass (modelled on maintain-verification-skill; references/adapted/maintain-verification-skill.md):
0. Locate the skill: the verify skill of the store, on the understando branch (else at HEAD).
1. Index hygiene: the shape check of create (missing, extra or dead feature entries).
2. Source wave: one brief for each feature file, for one read-only subagent each
   ($R/maintain/<feature>.md): the feature file, its source paths and the code of its checks. The
   subagents never drive the app and never edit a file.
3. Live pass, for each feature: the drive (launch, doctor, drive, cleanup) and every check of the
   feature run against the current code (HEAD, or --at), with the skill files taken from the
   understando branch. Then every control runs again.
4. Flags: a verifier that was proven and whose control no longer makes it fail (stale: it does not
   count now); a verifier that fails at the head (a product gap, or drift of the skill); a control
   whose anchor no longer resolves; a formal record whose code or model changed (drift).
5. Outcome: clean (no flag), changed (the flags name proven corrections: ship them as ONE change
   set on the understando branch, `understando create --spec FILE --yes` or one commit), or
   blocked (the pass could not finish: the report says what blocked it).

The commands show once and run only with --yes. maintain edits no product code.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import ops  # noqa: E402
import run_control  # noqa: E402
import store  # noqa: E402
import strength  # noqa: E402


def brief(data: dict, feat: dict, sk: str) -> str:
    checks = [v for v in data["checks"] if v.get("feature") == feat["id"]]
    code = [f"{r['path']}::{r.get('symbol', '')}" for v in checks for r in v.get("code", [])]
    return "\n".join([
        f"# Source read: {feat['name']}", "",
        "Read only. Do not drive the app and do not edit a file.", "",
        f"- The feature file: `{feat.get('file') or sk + '/features/' + feat['id'] + '.md'}`.",
        f"- The source paths: {', '.join(feat.get('paths') or ['(none named)'])}.",
        f"- The code of its checks: {', '.join(code) or '(none named)'}.", "",
        "Return four parts: the feature in two sentences; its source entry points; the doc drift that you see, "
        "each with a path and a line, or `none`; one live recipe to verify it.", ""])


def flags_for(before: dict, data: dict, fid: str | None) -> list[dict]:
    old = {v["id"]: v.get("state") for v in before.get("checks", [])}
    out = []
    for v in data["checks"]:
        if fid and v.get("feature") != fid:
            continue
        if v["state"] == "cannot-fail" and old.get(v["id"]) in ("proven", None):
            ks = [k["id"] for k in data["controls"] if k["check"] == v["id"]]
            out.append({"flag": "stale", "check": v["id"], "feature": v.get("feature"),
                        "detail": f"{v['id']} ({v.get('name', v['kind'])}): its control {', '.join(ks)} no longer makes it fail. "
                                  "It does not count now. Find what changed: a second guard elsewhere, a test that no longer reaches the code, or a control on dead code."})
        elif v["state"] in ("failing", "broken"):
            out.append({"flag": v["state"], "check": v["id"], "feature": v.get("feature"),
                        "detail": f"{v['id']} is {v['state']} at the head: a product gap (report it) or drift of the skill (fix the map)."})
    for k in data["controls"]:
        r = k.get("result") or {}
        if r.get("status") == "error" and "anchor" in (r.get("note") or ""):
            out.append({"flag": "stale-anchor", "check": k["check"], "detail": f"control {k['id']}: {r['note']}"})
    for v in data["checks"]:
        rec = v.get("formal_record") or {}
        if rec.get("drift") and (not fid or v.get("feature") == fid):
            import formal_record
            try:
                repo = Path(rec["drift"].get("root") or ".")
                now = formal_record.stamp_of(repo, [f["path"] for f in rec["drift"]["code_files"]], [f["path"] for f in rec["drift"]["model_files"]])
                if [f["blob"] for f in now["code_files"]] != [f["blob"] for f in rec["drift"]["code_files"]]:
                    out.append({"flag": "proof-drift", "check": v["id"], "detail": f"{v['id']}: the code of its proof changed. Run `understando formalize --recheck {rec.get('id') or v['id']}`."})
            except Exception:  # noqa: BLE001  a record of another checkout: no drift check here
                pass
    return out


def main(c: store.Ctx, argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="understando maintain", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--feature")
    ap.add_argument("--at", help="the code to verify (default: HEAD)")
    args = ap.parse_args(argv)
    repo = c.need_repo()
    data = c.need_data()
    sk = data.get("skill")
    if not sk:
        store.fail("maintain: the store names no verify skill. Run `understando create` first.", 2)
    tip = (data.get("ready") or {}).get("head") or "HEAD"
    import create
    hygiene = create.check_shape(repo, tip, sk)
    feats = [f for f in data["features"] if not args.feature or f["id"] == args.feature]
    if args.feature and not feats:
        store.fail(f"maintain: no feature {args.feature}", 2)
    (c.run / "maintain").mkdir(exist_ok=True)
    for f in feats:
        (c.run / "maintain" / f"{f['id']}.md").write_text(brief(data, f, sk), encoding="utf-8")
    ids = {v["id"] for v in data["checks"] if v.get("feature") in {f["id"] for f in feats}}
    cmds = [v["command"]["argv"] for v in data["checks"] if v["id"] in ids and "command" in v]
    if not store.confirm(c, "maintain (the live pass)", cmds):
        print(f"maintain: the source briefs are in {c.run / 'maintain'}: one read-only subagent for each.")
        return 0
    head = store.git(repo, "rev-parse", args.at or "HEAD")
    before = json.loads(json.dumps(data))
    strength.apply(before)
    data["head"] = head
    moved = {}
    for v in data["checks"]:
        if v["id"] in ids and v.get("at"):
            moved[v["id"]] = v.pop("at")
    paths = [sk] + ([f".claude/skills/{sk.rsplit('/', 1)[1]}"] if sk.startswith(".agents/") else [])
    run_control.OVERLAY[0] = (tip, paths) if tip != "HEAD" else None
    blocked = None
    try:
        with ops.scratch_clone(repo) as (clone, wt):
            run_control.run_baseline(data, clone, wt, ids, None, c.run / "evidence")
            for k in data["controls"]:
                if k["check"] in ids:
                    run_control.run_one(data, k, clone, wt)
    except RuntimeError as exc:
        blocked = str(exc)
    finally:
        run_control.OVERLAY[0] = None
        for vid, at in moved.items():
            store.find(data, "checks", vid)["at"] = at
    rep = strength.apply(data)
    flags = flags_for(before, data, args.feature)
    flags += [{"flag": "index", "detail": p} for p in hygiene]
    outcome = "blocked" if blocked else ("changed" if flags else "clean")
    data["maintained"] = {"at": head, "skill_at": tip, "ran_at": store.now(), "outcome": outcome, "flags": flags,
                          "features": [f["id"] for f in feats], **({"blocked": blocked} if blocked else {})}
    c.save(data)
    lines = [f"maintain: {outcome}: {len(feats)} features, {len(ids)} verifiers at {head[:10]} (the skill from {str(tip)[:10]})"]
    lines += [f"FLAG {f['flag'].upper()}: {f['detail']}" for f in flags]
    if blocked:
        lines.append(f"blocked: {blocked}")
    if outcome == "changed":
        lines.append("Fix each flag under the edit scope (the skill folder only; report a product gap, do not paper over it). "
                     "Re-drive each fix, then ship ONE change set: `understando create --verifier --yes` writes the Verifier sections again.")
    lines.append(f"source briefs: {c.run / 'maintain'}")
    store.emit(c, {**data["maintained"], "claims": rep["claims"]}, "\n".join(lines))
    return 0
