#!/usr/bin/env bash
# End-to-end test of the formalize sub-skills on a tiny Python repo (tests/formal/repo):
#   - withdraw (pure rule) + Lean model      -> must end Formal (theorems, axioms clean,
#                                               conformance green, model and code controls red);
#   - retry (small loop) + TLA+ spec         -> must end Formal (TLC green, planted spec red with
#                                               a trace, trace replay green, code control red);
#   - split_evenly (buggy) + proof attempt   -> must end Not formal, route code-first, with a
#                                               witness test that fails on the bug and passes on the fix.
# Then the drift gate goes red when the mapped code changes.
#
#   tests/formal/e2e.sh          KEEP=1 tests/formal/e2e.sh keeps the work dir
#
# Offline: needs lake (elan, Lean 4.34.1), java and tla2tools.jar, python3. No network, no model.
# The fixture's invariants are written in the fixture itself, so the run passes
# --invariant-author user --invariant-ref fixture:<file>; that stands in for the user's journal row.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIX="$ROOT/tests/formal"
S="$ROOT/scripts"
. "$ROOT/tests/isolate.sh" formal
WORK="$(mktemp -d "$UNDERSTANDO_TEST_ROOT/understando-formal-e2e.XXXXXX")"
REPO="$WORK/repo"
OUT="$WORK/out"
cleanup() { if [ "${KEEP:-0}" = 1 ]; then echo "kept $WORK"; else rm -rf "$WORK"; fi; isolate_cleanup; }
trap cleanup EXIT

step() { printf '\n== %s\n' "$*"; }
g() { git -C "$REPO" -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false "$@"; }
field() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2], {}, {'d': d}))" "$@"; }
expect() { [ "$2" = "$3" ] || { echo "FAIL: $1: expected '$3', got '$2'"; exit 1; }; echo "ok: $1 = $2"; }

step "build the fixture repo"
mkdir -p "$OUT"
cp -R "$FIX/repo" "$REPO"
rm -rf "$REPO/formal/lean/.lake"
g init -q -b main && g add -A && g commit -q -m "fixture"
LEAN="$REPO/formal/lean"
TLA="$REPO/formal/tla"

# ---------------------------------------------------------------- frog 1: withdraw (tier 5, Lean)
step "withdraw: lake build, axioms, theorem hashes"
python3 "$S/formal_lean.py" check --project "$LEAN" --import Fixture \
  --theorem Fixture.Wallet.withdraw_nonneg --theorem Fixture.Wallet.withdraw_le \
  --theorem Fixture.Wallet.withdraw_exact > "$OUT/w.check.json"
expect "withdraw check" "$(field "$OUT/w.check.json" "d['status']")" green

step "withdraw: the committed vectors match the model"
python3 "$S/formal_lean.py" vectors --project "$LEAN" --exe vectors --out "$LEAN/withdraw_vectors.jsonl" --check

step "withdraw: conformance (vectors + live Lean oracle on random inputs)"
ORACLE="$LEAN/.lake/build/bin/vectors"
python3 "$S/formal_run.py" --cwd "$REPO" --env FORMAL_ORACLE="$ORACLE" --env FORMAL_REQUIRE_ORACLE=1 \
  -- python3 -m unittest tests.test_conformance_wallet > "$OUT/w.conf.json"
expect "withdraw conformance" "$(field "$OUT/w.conf.json" "d['status']")" green

step "withdraw: model control (a planted wrong guard breaks the theorem)"
python3 "$S/formal_lean.py" control --project "$LEAN" --file Fixture/Wallet.lean \
  --symbol withdraw --match "/amount > (balance) then/" --with "balance + 1" --pattern "withdraw|omega" > "$OUT/w.k1.json"
expect "withdraw model control" "$(field "$OUT/w.k1.json" "d['status']")" red

step "withdraw: code control (a planted wrong function breaks conformance)"
python3 "$S/formal_run.py" --cwd "$REPO" --copy "$REPO" --expect red --pattern "AssertionError" \
  --env FORMAL_ORACLE="$ORACLE" --env FORMAL_REQUIRE_ORACLE=1 \
  --edit '{"op":"replace-with","path":"mini/wallet.py","symbol":"withdraw","match":"/amount (>) balance:/","with":">="}' \
  -- python3 -m unittest tests.test_conformance_wallet > "$OUT/w.k2.json" || true
expect "withdraw code control" "$(field "$OUT/w.k2.json" "d['status']")" red

python3 "$S/formal_record.py" build --out "$OUT/F01.json" --id F01 --kind lean --tier 5 --claim C1 \
  --description "withdraw never overdraws and debits exactly or not at all." \
  --check "$OUT/w.check.json" --conformance "$OUT/w.conf.json" \
  --control model:K01:"$OUT/w.k1.json" --control code:K02:"$OUT/w.k2.json" \
  --card "$FIX/cards/withdraw.card.json" --checks7 "$FIX/cards/withdraw.checks7.json" \
  --invariant-author user --invariant-ref fixture:formal/lean/Fixture/Wallet.lean >/dev/null
python3 "$S/formal_record.py" stamp --record "$OUT/F01.json" --repo "$REPO" --code mini/wallet.py \
  --model formal/lean/Fixture/Wallet.lean formal/lean/withdraw_vectors.jsonl >/dev/null

# ---------------------------------------------------------------- frog 2: retry (tier 4, TLA+)
step "retry: TLC (deadlock check on, invariants, Termination)"
python3 "$S/formal_tlc.py" check --spec "$TLA/Retry.tla" --cfg "$TLA/Retry.cfg" > "$OUT/r.check.json"
expect "retry TLC" "$(field "$OUT/r.check.json" "d['status']")" green

step "retry: planted spec (guard removed) must violate an invariant with a trace"
python3 "$S/formal_tlc.py" control --spec "$TLA/Retry.tla" --cfg "$TLA/Retry.cfg" \
  --symbol Call --match '/== (\/\\ result = "running")/' --with TRUE --pattern NoCallAfterStop > "$OUT/r.k1.json"
expect "retry spec control" "$(field "$OUT/r.k1.json" "d['status']")" red
expect "retry spec control trace length > 1" "$(field "$OUT/r.k1.json" "len(d['trace']) > 1")" True
field "$OUT/r.k1.json" "' -> '.join(str(s['state']) for s in d['trace'])"

step "retry: vectors from TLC terminal states match the committed file, then replay"
python3 "$S/formal_tlc.py" vectors --spec "$TLA/Retry.tla" --cfg "$TLA/RetryVectors.cfg" \
  --done 'result!="running"' --out "$TLA/retry_vectors.json" --check
python3 "$S/formal_run.py" --cwd "$REPO" -- python3 -m unittest tests.test_conformance_retry > "$OUT/r.conf.json"
expect "retry trace replay" "$(field "$OUT/r.conf.json" "d['status']")" green

step "retry: code control (drop the fatal stop) breaks the replay"
python3 "$S/formal_run.py" --cwd "$REPO" --copy "$REPO" --expect red --pattern "AssertionError|IndexError" \
  --edit '{"op":"delete-line","path":"mini/retry.py","symbol":"retry","match":"if outcome == \"fatal\":"}' \
  -- python3 -m unittest tests.test_conformance_retry > "$OUT/r.k2.json" || true
expect "retry code control" "$(field "$OUT/r.k2.json" "d['status']")" red

python3 "$S/formal_record.py" build --out "$OUT/F02.json" --id F02 --kind tla --tier 4 --claim C2 \
  --description "retry makes at most MaxTries calls, none after ok or fatal, and returns." \
  --check "$OUT/r.check.json" --conformance "$OUT/r.conf.json" \
  --control model:K03:"$OUT/r.k1.json" --control code:K04:"$OUT/r.k2.json" \
  --card "$FIX/cards/retry.card.json" --checks7 "$FIX/cards/retry.checks7.json" \
  --invariant-author user --invariant-ref fixture:formal/tla/Retry.tla >/dev/null
python3 "$S/formal_record.py" stamp --record "$OUT/F02.json" --repo "$REPO" --code mini/retry.py \
  --model formal/tla/Retry.tla formal/tla/Retry.cfg formal/tla/retry_vectors.json >/dev/null

# ---------------------------------------------------------------- frog 3: split_evenly (buggy)
step "split: the proof attempt hits its first hard blocker"
python3 "$S/formal_lean.py" attempt --project "$LEAN" --file Attempt/SplitSum.lean > "$OUT/s.attempt.json" || true
expect "split attempt" "$(field "$OUT/s.attempt.json" "d['status']")" red

step "split: extract the witness and route the blocker"
"$LEAN/.lake/build/bin/split_witness" > "$OUT/s.witness.json"
cat "$OUT/s.witness.json"
python3 "$S/formal_witness.py" route --attempt "$OUT/s.attempt.json" --witness "$OUT/s.witness.json" \
  --model-is-code > "$OUT/s.route.json"
expect "split route" "$(field "$OUT/s.route.json" "d['route']")" code-first

step "split: the witness becomes a regression test that fails on the bug"
python3 "$S/formal_witness.py" test --witness "$OUT/s.witness.json" --claim "sum(result) == total" \
  --out "$REPO/tests/test_witness_split_evenly.py" >/dev/null
python3 "$S/formal_run.py" --cwd "$REPO" --pattern "the claim sum\(result\) == total does not hold" \
  -- python3 -m unittest tests.test_witness_split_evenly > "$OUT/s.wtest.json" || true
expect "witness test on the bug" "$(field "$OUT/s.wtest.json" "d['status']")" red
python3 "$S/formal_run.py" --cwd "$REPO" --copy "$REPO" --expect green \
  --edit '{"op":"replace-with","path":"mini/split.py","symbol":"split_evenly","match":"/i (<=) remainder/","with":"<"}' \
  -- python3 -m unittest tests.test_witness_split_evenly > "$OUT/s.wfix.json"
expect "witness test on the fix" "$(field "$OUT/s.wfix.json" "d['status']")" green

python3 "$S/formal_record.py" build --out "$OUT/F03.json" --id F03 --kind lean --tier 5 --claim C3 \
  --description "split_evenly parts sum to the total." \
  --check "$OUT/s.attempt.json" --conformance "$OUT/s.wtest.json" --route code-first --blocker-open \
  --witness "$OUT/s.witness.json" --witness-test "$OUT/s.wtest.json" --card "$FIX/cards/split.card.json" >/dev/null

# ---------------------------------------------------------------- verdicts, sidecar, drift
step "verdicts"
SIDE="$OUT/formal/verifiers.json"
for r in F01 F02 F03; do
  python3 "$S/formal_record.py" add --sidecar "$SIDE" --record "$OUT/$r.json" --repo fixture --pr 1 --head "$(g rev-parse HEAD)" >/dev/null
done
expect "F01 withdraw" "$(field "$OUT/F01.json" "d['formal']['verdict']")" Formal
expect "F02 retry" "$(field "$OUT/F02.json" "d['formal']['verdict']")" Formal
expect "F03 split" "$(field "$OUT/F03.json" "d['formal']['verdict']")" "Not formal"
expect "F03 bug in the PR" "$(field "$OUT/F03.json" "d['route'] + ' ' + str(d['witness']['args'])")" "code-first {'total': 0, 'parts': 1}"

step "an agent-proposed invariant is never Formal"
python3 - "$OUT/F01.json" "$OUT/F01p.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d["invariant"] = {"author": "agent", "ref": None, "status": "proposed"}
json.dump(d, open(sys.argv[2], "w"))
PY
python3 "$S/formal_record.py" verdict --record "$OUT/F01p.json" >/dev/null || true
expect "F01 proposed" "$(field "$OUT/F01p.json" "d['formal']['verdict']")" "Formal (pending user confirmation)"

step "drift gate"
python3 "$S/formal_record.py" drift --record "$OUT/F01.json" --repo "$REPO" > "$OUT/d1.json"
expect "drift at the stamp" "$(field "$OUT/d1.json" "d['status']")" green
sed -i.bak 's/amount <= 0/amount < 0/' "$REPO/mini/wallet.py" && rm "$REPO/mini/wallet.py.bak"
g commit -q -am "change the guard"
python3 "$S/formal_record.py" drift --record "$OUT/F01.json" --repo "$REPO" > "$OUT/d2.json" || true
expect "drift after a code change" "$(field "$OUT/d2.json" "d['status']")" red

step "summary"
python3 - "$SIDE" <<'PY'
import json, sys
for v in json.load(open(sys.argv[1]))["verifiers"]:
    ctl = ", ".join(f"{c['id']}({c['target']})={c['result']['status']}" for c in v["controls"])
    print(f"{v['id']} {v['kind']} tier {v['ladder_tier']}: {v['formal']['verdict']}; route {v['route']}; "
          f"conformance {v['conformance']['result']['status']}; controls [{ctl}]")
PY
echo "PASS: formal e2e"
