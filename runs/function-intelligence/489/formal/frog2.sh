#!/usr/bin/env bash
# Frog 2 (#489): the edit-round loop's stop rules and the finish gate, TLA+ tier 4.
#   FI=<function-intelligence worktree at understando/489-ready> bash frog2.sh
set -euo pipefail
U="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FI="${FI:-/Users/clayton/dev/function-intelligence/.claude/worktrees/understando-489-ready}"
P="$FI/projects/clinical-reasoning"
T="$P/formal/tla"
O="$HERE/work"; mkdir -p "$O"
tlc() { python3 "$U/scripts/formal_tlc.py" "$@"; }
st() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['status'], d.get('violation') or '', d.get('matched'))" "$1"; }

# Model checks: both accept rules, and the finish gate.
tlc check --spec "$T/DocLoop.tla" --cfg "$T/DocLoop.cfg" > "$O/l.check.si.json" || true
tlc check --spec "$T/DocLoop.tla" --cfg "$T/DocLoopLC.cfg" > "$O/l.check.lc.json" || true
tlc check --spec "$T/Finish.tla" --cfg "$T/Finish.cfg" > "$O/f.check.json" || true
# Claim C15 as the PR body words it (no "finished"): expected red, with a witness trace.
tlc check --spec "$T/DocLoop.tla" --cfg "$T/DocLoopC15.cfg" > "$O/l.c15.json" || true

# Planted wrong specs: each removes one guard; TLC must report the matching violation.
tlc control --spec "$T/DocLoop.tla" --cfg "$T/DocLoop.cfg" --pattern UnfixableStops \
  --find '           ELSE IF Unfixable(C) THEN "unfixable"
           ELSE IF edited' --replace '           ELSE IF edited' > "$O/l.k1.json" || true
tlc control --spec "$T/DocLoop.tla" --cfg "$T/DocLoop.cfg" --pattern LostIsFinal \
  --find "     THEN /\\ lost' = TRUE /\\ phase' = \"floor\"
          /\\ log' = Append(log, EditEvent(\"review\"" \
  --replace "     THEN /\\ lost' = TRUE /\\ phase' = \"review\"
          /\\ log' = Append(log, EditEvent(\"review\"" > "$O/l.k2.json" || true
tlc control --spec "$T/DocLoop.tla" --cfg "$T/DocLoop.cfg" --pattern IdleFinishedStops \
  --find 'IF ~k /\ o = "finished" /\ ~ch ' --replace 'IF FALSE ' > "$O/l.k3.json" || true
tlc control --spec "$T/Finish.tla" --cfg "$T/Finish.cfg" --pattern RefusalsBounded \
  --find 'IF b /\ refusals < MaxRefusals' --replace 'IF b' > "$O/f.k1.json" || true

# The committed vectors still match the specs (drift gate for the vectors).
tlc vectors --spec "$T/DocLoop.tla" --cfg "$T/DocLoopVectorsSI.cfg" --done 'phase="done"' --keep log --out "$T/docloop_vectors_SI.json" --check
tlc vectors --spec "$T/DocLoop.tla" --cfg "$T/DocLoopVectorsLC.cfg" --done 'phase="done"' --keep log --out "$T/docloop_vectors_LC.json" --check
for t in 3 6; do
  tlc vectors --spec "$T/Finish.tla" --cfg "$T/FinishVectorsT$t.cfg" --done 'stop!="running"' --keep log --keep stop \
    --keep refusals --keep withBlocking --out "$T/finish_vectors_t$t.json" --check
done

# Trace replay through the real code.
python3 "$U/scripts/formal_run.py" --cwd "$P" -- uv run --no-sync pytest -q tests/test_formal_docloop_replay.py > "$O/l.conf.json" || true
python3 "$U/scripts/formal_run.py" --cwd "$P" -- uv run --no-sync pytest -q tests/test_formal_finish_replay.py > "$O/f.conf.json" || true

# Planted wrong code: each must make the replay red.
code() { local out="$1" test="$2" edit="$3"
  python3 "$U/scripts/formal_run.py" --cwd "$P" --copy "$P" --link .venv --expect red --pattern "AssertionError|assert" \
    --edit "$edit" -- uv run --no-sync pytest -q -x "$test" > "$O/$out.json" || true; }
code l.k4 tests/test_formal_docloop_replay.py \
  '{"op":"replace","path":"src/cr/docgen/loop.py","find":"        elif _idle(record):\n            break\n","replace":""}'
code l.k5 tests/test_formal_docloop_replay.py \
  '{"op":"replace","path":"src/cr/docgen/loop.py","find":"        if record.lost:\n            lost = record\n            break\n        before = current\n","replace":"        before = current\n"}'
code l.k6 tests/test_formal_docloop_replay.py \
  '{"op":"replace","path":"src/cr/docgen/loop.py","find":"not editable(current.findings) or _unfixable(current):","replace":"not editable(current.findings):"}'
code f.k2 tests/test_formal_finish_replay.py \
  '{"op":"replace","path":"src/cr/docgen/session.py","find":"if blocking and self.run.finish_refusals < self.spec.max_finish_refusals:","replace":"if blocking:"}'

for k in l.check.si l.check.lc f.check l.c15 l.k1 l.k2 l.k3 f.k1 l.conf f.conf l.k4 l.k5 l.k6 f.k2; do
  printf '%s: %s\n' "$k" "$(st "$O/$k.json")"
done
