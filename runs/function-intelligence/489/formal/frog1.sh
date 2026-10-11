#!/usr/bin/env bash
# Frog 1 (#489): the accept rule, Lean tier 5. Reproduces every artifact under work/.
#   FI=<function-intelligence worktree at understando/489-ready> bash frog1.sh
set -euo pipefail
U="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FI="${FI:-/Users/clayton/dev/function-intelligence/.claude/worktrees/understando-489-ready}"
P="$FI/projects/clinical-reasoning"
L="$P/formal/lean"
O="$HERE/work"; mkdir -p "$O"
TH=()
for t in lexLt_irrefl lexLt_trans lexLt_asymm lexLt_total keepSI_iff keepSI_no_new_severe keepSI_no_new_det \
         keepSI_strict keepSI_unchanged rejectsEarlySI_sound keepLC_always rejectsEarlyLC_never \
         settleLC_some settleLC_stands settleLC_none settleSI_none; do TH+=(--theorem "Accept.$t"); done

python3 "$U/scripts/formal_lean.py" check --project "$L" --import Accept "${TH[@]}" > "$O/a.check.json"
python3 "$U/scripts/formal_lean.py" vectors --project "$L" --exe vectors --out "$L/accept_vectors.jsonl" --check
ORACLE="$L/.lake/build/bin/vectors"
TEST=tests/test_formal_accept_conformance.py
python3 "$U/scripts/formal_run.py" --cwd "$P" --env FORMAL_ACCEPT_ORACLE="$ORACLE" \
  -- uv run --no-sync pytest -q -rs "$TEST" > "$O/a.conf.json"

# Model controls: a planted wrong model must break a theorem.
python3 "$U/scripts/formal_lean.py" control --project "$L" --file Accept/Model.lean \
  --find "else (cleanIdx states).getLast?" --replace "else (cleanIdx states).head?" \
  --pattern "error: Accept/Theorems.lean:[0-9]+" > "$O/a.k1.json" || true
python3 "$U/scripts/formal_lean.py" control --project "$L" --file Accept/Model.lean \
  --find "  else if newKey (severeKeys after) (severeKeys before) then false
" --replace "" --pattern "error: Accept/Theorems.lean:[0-9]+" > "$O/a.k2.json" || true
# Code controls: a planted wrong function must break conformance.
python3 "$U/scripts/formal_run.py" --cwd "$P" --copy "$P" --link .venv --expect red --pattern "AssertionError|assert" \
  --env FORMAL_ACCEPT_ORACLE="$ORACLE" \
  --edit '{"op":"replace","path":"src/cr/docgen/accept.py","find":"return clean[-1] if clean else None","replace":"return clean[0] if clean else None"}' \
  -- uv run --no-sync pytest -q -x "$TEST" > "$O/a.k3.json" || true
python3 "$U/scripts/formal_run.py" --cwd "$P" --copy "$P" --link .venv --expect red --pattern "AssertionError|assert" \
  --env FORMAL_ACCEPT_ORACLE="$ORACLE" \
  --edit '{"op":"replace","path":"src/cr/docgen/accept.py","find":"        if severe_confirmed_keys(after) - severe_confirmed_keys(before):\n            return False\n","replace":""}' \
  -- uv run --no-sync pytest -q -x "$TEST" > "$O/a.k4.json" || true
for k in a.check a.conf a.k1 a.k2 a.k3 a.k4; do
  printf '%s: %s\n' "$k" "$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['status'], d.get('matched'))" "$O/$k.json")"
done
