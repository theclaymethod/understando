#!/usr/bin/env bash
# Build, stamp and rate the #489 artifact records, and write the sidecar verifiers.json.
# Run after frog1.sh and frog2.sh.   FI=<function-intelligence worktree> bash records.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$HERE"
U="$(cd ../../../.. && pwd)"
FI="${FI:-/Users/clayton/dev/function-intelligence/.claude/worktrees/understando-489-ready}"
R() { python3 "$U/scripts/formal_record.py" "$@"; }
W=work; I=inputs; S=verifiers.json; P=projects/clinical-reasoning
HEAD=3758b0901c4f85ad955e1a6f0cb02804c838147b
rm -f "$S"

python3 - <<'PY'
import json
t = json.load(open("work/l.c15.trace.json")); r = json.load(open("work/l.c15.replay.json"))
json.dump({"kind": "tlc-trace", "property": "IdleStops (C15 as the PR body words it)", "cfg": "formal/tla/DocLoopC15.cfg",
           "input": {"rule": "StrictImprovement", "projection_findings": ["m: confirmed S4, blocking, editable"],
                     "round_1": "editor stops at turn_limit, changes no file; not kept",
                     "round_2": "runs (in the trace the model then loses the call)"},
           "trace": t["log"], "replay_on_real_code": r}, open("work/l.c15.witness.json", "w"), indent=1)
inv = json.load(open("inputs/loop.invariants.json"))
json.dump([i for i in inv if i["id"] != "L5"], open("work/loop2.invariants.json", "w"), indent=1)
json.dump([i for i in inv if i["id"] == "L5"], open("work/loop3.invariants.json", "w"), indent=1)
PY

R build --out $W/F489-1.json --id F489-1 --kind lean --tier 5 --claim C20 --claim FC1 --claim FC2 --claim FC3 \
  --description "Lean model of cr.docgen.accept: score order, StrictImprovement keep and rejects_early, LastClean keep and settle." \
  --check $W/a.check.json --conformance $W/a.conf.json \
  --control model:K489-1a:$W/a.k1.json --control model:K489-1b:$W/a.k2.json \
  --control code:K489-1c:$W/a.k3.json --control code:K489-1d:$W/a.k4.json \
  --card $I/accept.card.json --checks7 $I/accept.checks7.json --invariants $I/accept.invariants.json
R build --out $W/F489-2.json --id F489-2 --kind tla --tier 4 --claim C15 --claim C16 --claim C17 --claim FC4 --claim FC5 \
  --description "TLA+ model of run_document: stop rules, lost call, settle, release audit and floor, for both accept rules." \
  --check $W/l.check.si.json --conformance $W/l.conf.json \
  --control model:K489-2a:$W/l.k1.json --control model:K489-2b:$W/l.k2.json --control model:K489-2c:$W/l.k3.json \
  --control code:K489-2d:$W/l.k4.json --control code:K489-2e:$W/l.k5.json --control code:K489-2f:$W/l.k6.json \
  --route theorem-first --witness $W/l.c15.witness.json \
  --card $I/loop.card.json --checks7 $I/loop.checks7.json --invariants $W/loop2.invariants.json
R build --out $W/F489-3.json --id F489-3 --kind tla --tier 4 --claim C18 \
  --description "TLA+ model of the editor session's finish gate: refusals while a code check blocks, at most max_finish_refusals." \
  --check $W/f.check.json --conformance $W/f.conf.json \
  --control model:K489-3a:$W/f.k1.json --control code:K489-3b:$W/f.k2.json \
  --card $I/loop.card.json --checks7 $I/loop.checks7.json --invariants $W/loop3.invariants.json

python3 - <<'PY'
import json
r = json.load(open("work/F489-2.json")); lc = json.load(open("work/l.check.lc.json"))
r["check_more"] = [{k: lc.get(k) for k in ("status", "spec", "cfg", "cfg_sha256", "distinct", "deadlock_checked")}]
r["route_reason"] = ("C15 as the PR body words it (no 'finished') fails in TLC; the code's _idle needs a finished "
                     "session (loop.py:101-107). The claim overstates, so the checked property is IdleFinishedStops, "
                     "which holds; the witness replays the same decisions on the real loop.")
json.dump(r, open("work/F489-2.json", "w"), indent=2)
r = json.load(open("work/F489-3.json"))
r["card"] = dict(r["card"], frog="docgen.session.finish_gate",
                 surface="projects/clinical-reasoning/src/cr/docgen/session.py:102-138, 255-265",
                 artifact="formal/tla/Finish.tla + cfgs; finish_vectors_t{3,6}.json; tests/test_formal_finish_replay.py")
json.dump(r, open("work/F489-3.json", "w"), indent=2)
PY

R stamp --record $W/F489-1.json --repo "$FI" --code $P/src/cr/docgen/accept.py $P/src/cr/docgen/findings.py \
  --model $P/formal/lean/Accept/Model.lean $P/formal/lean/Accept/Theorems.lean $P/formal/lean/Vectors.lean \
          $P/formal/lean/accept_vectors.jsonl $P/tests/test_formal_accept_conformance.py
R stamp --record $W/F489-2.json --repo "$FI" --code $P/src/cr/docgen/loop.py $P/src/cr/docgen/accept.py $P/src/cr/docgen/adapter.py \
  --model $P/formal/tla/DocLoop.tla $P/formal/tla/DocLoop.cfg $P/formal/tla/DocLoopLC.cfg $P/formal/tla/DocLoopVectorsSI.cfg \
          $P/formal/tla/DocLoopVectorsLC.cfg $P/formal/tla/docloop_vectors_SI.json $P/formal/tla/docloop_vectors_LC.json \
          $P/tests/test_formal_docloop_replay.py
R stamp --record $W/F489-3.json --repo "$FI" --code $P/src/cr/docgen/session.py \
  --model $P/formal/tla/Finish.tla $P/formal/tla/Finish.cfg $P/formal/tla/finish_vectors_t3.json \
          $P/formal/tla/finish_vectors_t6.json $P/tests/test_formal_finish_replay.py
for r in F489-1 F489-2 F489-3; do
  R verdict --record $W/$r.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['id'], '|', d['verdict'], '|', d['missing'])" || true
  R add --sidecar $S --record $W/$r.json --repo function-intelligence --pr 489 --head $HEAD --proposed-claims $I/claims.json >/dev/null
  R drift --record $W/$r.json --repo "$FI"
done
