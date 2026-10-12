#!/usr/bin/env bash
# The end-to-end test of the kept loop, on the fixture repo (tests/fixture):
#   create    generates verify-wallet with a feature map, proves one feature end to end (the drive,
#             the evidence kept after cleanup, the control fails), and its Verifier section names
#             the bar and the verifiers;
#   discover  records the user's invariant (and a possible bug from an example answer);
#   build     drafts a check that fails on a planted bug, then passes on the code;
#   probe     a planted control goes red; a check that cannot fail is flagged;
#   mutate    mutmut reports killed, survived and filtered mutants with a kill matrix; cosmic-ray
#             runs on the riskiest changed lines;
#   snippet   resolves a code ref and gives its permalink;
#   export    writes verify-data.json and refs.resolved.json for visual-explainer;
#   maintain  flags the drive whose control no longer fails after a code change.
# Then tests/formal/e2e.sh: Lean and TLA+ to Formal, the sync into the store, and recheck.
#
#   tests/e2e.sh            KEEP=1 tests/e2e.sh keeps the work dir; SKIP_FORMAL=1 skips the formal e2e
#
# No model call, no network. The mutation venv (`understando setup --mutation`) must exist.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIX="$ROOT/tests/fixture"
. "$ROOT/tests/isolate.sh" e2e
isolate_snapshot "$UNDERSTANDO_TEST_ROOT/real-before.sha256"
# The mutation venv lives in the real store; the tests run its programs, they never write there.
export UNDERSTANDO_MUTATION_VENV="${UNDERSTANDO_MUTATION_VENV:-$ISOLATE_REAL_STORE/tools/mutation}"
WORK="$(mktemp -d "$UNDERSTANDO_TEST_ROOT/understando-e2e.XXXXXX")"
REPO="$WORK/wallet"
OUT="$WORK/out"; mkdir -p "$OUT"
cleanup() { if [ "${KEEP:-0}" = 1 ]; then echo "kept $WORK"; else rm -rf "$WORK"; fi; isolate_cleanup; }
trap cleanup EXIT

U() { "$ROOT/bin/understando" --repo "$REPO" "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "FAIL: $*"; exit 1; }
has() { grep -qF -- "$2" "$1" || { echo "--- $1"; cat "$1"; fail "$1 lacks: $2"; }; }
lacks() { if grep -qF -- "$2" "$1"; then echo "--- $1"; cat "$1"; fail "$1 has: $2"; fi; }
field() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2], {'d': d}))" "$@"; }
expect() { [ "$2" = "$3" ] || fail "$1: expected '$3', got '$2'"; echo "ok: $1 = $2"; }
g() { git -C "$REPO" -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false "$@"; }

step "isolation: the guard refuses a planted write and a read of the real data (tests/isolate-e2e.sh)"
WORK="$WORK" bash "$ROOT/tests/isolate-e2e.sh"

step "the fixture repo: a base commit, then the work"
mkdir -p "$REPO" && cp -R "$FIX/base/." "$REPO/"
g init -q -b main && g remote add origin https://github.com/fixture/wallet.git
g add -A && g commit -q -m "base"
BASE="$(g rev-parse HEAD)"
cp -R "$FIX/head/." "$REPO/" && g add -A && g commit -q -m "Refuse overdrafts in the wallet"
HEAD="$(g rev-parse HEAD)"
RUN="$UNDERSTANDO_RUNS/wallet/wallet"
STATUS_BEFORE="$(g status --porcelain)"

# ------------------------------------------------------------------------------------------ create
step "create: the interview finds the CLI and the repo's own test command"
U create > "$OUT/interview.txt"
has "$OUT/interview.txt" "cli (wallet/__main__.py)"
has "$OUT/interview.txt" '`python3 -m unittest discover -s tests -t .` (AGENTS.md:'
has "$OUT/interview.txt" "verify skills already here: none"

step "create --spec: it shows what it writes, and writes nothing without --yes"
U create --spec "$FIX/create.spec.json" > "$OUT/create-ask.txt"
has "$OUT/create-ask.txt" ".agents/skills/verify-wallet/features/withdraw.md"
has "$OUT/create-ask.txt" "Repeat the same command with --yes"
[ -z "$(g branch --list understando/verify-wallet)" ] || fail "create wrote a branch without --yes"

step "create --spec --yes: the skill on the branch understando/verify-wallet, never in the user's commits"
U --yes create --spec "$FIX/create.spec.json" > "$OUT/create.txt"
has "$OUT/create.txt" "on understando/verify-wallet at"
TIP="$(g rev-parse understando/verify-wallet)"
[ "$(g rev-parse main)" = "$HEAD" ] || fail "create moved main"
[ "$(g status --porcelain)" = "$STATUS_BEFORE" ] || fail "create changed the checkout"
g ls-tree -r --name-only "$TIP" -- .agents .claude | sort > "$OUT/tree.txt"
cat "$OUT/tree.txt"
for f in .agents/skills/verify-wallet/SKILL.md .agents/skills/verify-wallet/helpers/verify \
         .agents/skills/verify-wallet/features/README.md .agents/skills/verify-wallet/features/withdraw.md .claude/skills/verify-wallet; do
  has "$OUT/tree.txt" "$f"
done
expect "the .claude link is relative" "$(g cat-file -p "$TIP:.claude/skills/verify-wallet")" "../../.agents/skills/verify-wallet"
g show "$TIP:.agents/skills/verify-wallet/features/withdraw.md" > "$OUT/withdraw-1.md"
has "$OUT/withdraw-1.md" "## Verifier"
has "$OUT/withdraw-1.md" "**Surface:** backend."
has "$OUT/withdraw-1.md" "**Code Contracts:**"

step "create --check: the shape of the skill holds"
U create --check > "$OUT/check.txt"
has "$OUT/check.txt" "the shape holds."

step "create --prove withdraw: launch, doctor, drive, cleanup; the evidence survives; the control fails the drive"
U create --prove withdraw > "$OUT/prove-ask.txt"
has "$OUT/prove-ask.txt" "helpers/verify drive withdraw"
U --yes create --prove withdraw > "$OUT/prove.txt"
cat "$OUT/prove.txt"
has "$OUT/prove.txt" "prove withdraw: cleanup: ok"
has "$OUT/prove.txt" "evidence after cleanup: 2 files"
has "$OUT/prove.txt" "control K1 on V1: red"
has "$OUT/prove.txt" "PASS: the skill ran end to end"
EV="$(field "$RUN/verify.json" "d['proved']['evidence'][0]")"
test -s "$EV" || fail "the evidence $EV is gone"
has "$EV" "python3 -m wallet withdraw"

# ---------------------------------------------------------------------------------------- discover
step "discover: candidates and edge-case questions for the withdraw feature"
U discover --feature withdraw > "$OUT/discover.txt"
U --json discover questions > "$OUT/questions.json"
GUARD="$(field "$OUT/questions.json" "next(r['id'] for r in d['open'] if 'raises OverdraftError' in r['text'])")"
RESULT="$(field "$OUT/questions.json" "next(r['id'] for r in d['open'] if 'returns balance - amount' in r['text'])")"
field "$OUT/questions.json" "'\n'.join(q for r in d['open'] if r['id'] == '$GUARD' for q in r['questions'])"
sed -e "s/\"GUARD\"/\"$GUARD\"/" -e "s/\"RESULT\"/\"$RESULT\"/" "$FIX/answers.json" > "$OUT/answers.json"

step "discover answer: the user's invariant, an agent-picked one, and a possible bug from an example"
U discover answer --answers "$OUT/answers.json" > "$OUT/answer.txt"
cat "$OUT/answer.txt"
has "$OUT/answer.txt" "as I1 (accepted, author user"
has "$OUT/answer.txt" "as I2 (proposed, author agent"
has "$OUT/answer.txt" "P2 — [Small fix, 90% finding confidence, 85% fix confidence] The wallet refuses an amount above the balance."
has "$OUT/answer.txt" "Expected: raises ValueError. Actual: 15."
has "$OUT/answer.txt" "DONE: every candidate has a decision."
expect "I1 author" "$(field "$RUN/verify.json" "next(i['author'] for i in d['invariants'] if i['id'] == 'I1')")" user

# ------------------------------------------------------------------------------------------- build
step "build claim: the bar of a backend feature asks for a property test, types, a contract or an import rule"
U build claim --invariant I1 > "$OUT/claim.txt"
has "$OUT/claim.txt" "backend rule: a property test, types, a @cc contract or an import rule"
CL="$(field "$RUN/verify.json" "next(c['id'] for c in d['claims'] if c.get('invariants') == ['I1'])")"

step "build check: the @cc contract and the test that checks it"
U build check --claim "$CL" --kind contract --cc-id no-overdraft --name "the overdraft refusal test" \
  --command "python3 -m unittest tests.test_core.OverdraftTest" --code "tests/test_core.py::OverdraftTest" > "$OUT/bcheck.txt"
V="$(field "$RUN/verify.json" "d['checks'][-1]['id']")"
U build > "$OUT/status1.txt"
has "$OUT/status1.txt" "[x] 1. invariant"
has "$OUT/status1.txt" "[ ] 4. red"

step "build red: the check must fail on a planted bug (the guard deleted)"
PLANT='{"op":"delete-line","path":"wallet/core.py","symbol":"withdraw","match":"if amount > balance:"}'
U build red --check "$V" --plant "$PLANT" > "$OUT/red-ask.txt"
has "$OUT/red-ask.txt" "python3 -m unittest tests.test_core.OverdraftTest"
U --yes build red --check "$V" --plant "$PLANT" > "$OUT/red.txt"
has "$OUT/red.txt" "build red $V: red"

step "build green: the check passes on the code"
U --yes build green --check "$V" > "$OUT/green.txt"
has "$OUT/green.txt" "build green $V: green"
U build --feature withdraw > "$OUT/status2.txt"
has "$OUT/status2.txt" "DONE: every step holds."

# ------------------------------------------------------------------------------------------- probe
step "probe: a check that cannot fail, next to the good one"
U build check --claim "$CL" --kind property --name "the int type test" --command "python3 -m unittest tests.test_core.BalanceTest" > /dev/null
WEAK="$(field "$RUN/verify.json" "d['checks'][-1]['id']")"
U --yes build red --check "$WEAK" --plant "$PLANT" > "$OUT/red-weak.txt" || true
has "$OUT/red-weak.txt" "The check did not fail"
U --yes probe --feature withdraw > "$OUT/probe.txt"
cat "$OUT/probe.txt"
has "$OUT/probe.txt" "on $V: red"
has "$OUT/probe.txt" "FLAG CANNOT-FAIL: $WEAK stayed green on each control"
has "$OUT/probe.txt" "$CL   Proven  tier 3  meets its bar"

step "probe mutate (mutmut): killed, survived and filtered mutants, with the kill matrix"
U --yes probe mutate --feature withdraw --paths wallet/core.py > "$OUT/mutmut.txt"
cat "$OUT/mutmut.txt"
M1="$(field "$RUN/verify.json" "d['mutation'][-1]['id']")"
SUM="$RUN/verify.json"
[ "$(field "$SUM" "d['mutation'][-1]['summary'].get('killed', 0) >= 1")" = True ] || fail "no killed mutant"
[ "$(field "$SUM" "d['mutation'][-1]['summary'].get('survived', 0) >= 1")" = True ] || fail "no survived mutant"
expect "the message mutant is filtered" "$(field "$SUM" "[m['filter'] for m in d['mutation'][-1]['mutants'] if m.get('filter')]")" "['message-text']"
expect "the boundary mutant survives" "$(field "$SUM" "[m['line'] for m in d['mutation'][-1]['mutants'] if m['status'] == 'survived' and not m.get('filter')]")" "[13]"
expect "the kill matrix names the exact test" "$(field "$SUM" "sorted({t for row in d['mutation'][-1]['matrix'].values() for t, x in row.items() if x == 'killed'})")" \
  "['tests/test_core.py::ExactTest::test_withdraw_debits_the_amount']"
has "$OUT/mutmut.txt" "SURVIVED"

step "probe mutate (cosmic-ray): the riskiest changed lines, per-test coverage, the kill matrix"
U --yes probe mutate --tool cosmic-ray --feature withdraw --paths wallet/core.py --base "$BASE" > "$OUT/cr.txt"
cat "$OUT/cr.txt"
expect "the targeted lines" "$(field "$SUM" "d['mutation'][-1]['lines']")" "{'wallet/core.py': [13, 14]}"
[ "$(field "$SUM" "d['mutation'][-1]['summary'].get('killed', 0) >= 1 and d['mutation'][-1]['summary'].get('survived', 0) >= 1")" = True ] \
  || fail "cosmic-ray: no killed and survived mutants"
expect "only covering tests ran" "$(field "$SUM" "all(set(r) <= set(m['tests']) for m in d['mutation'][-1]['mutants'] for r in [d['mutation'][-1]['matrix'].get(m['id'], {})])")" True
lacks "$OUT/cr.txt" "test_cli"

# ------------------------------------------------------------------------------------ the explainer
step "create --verifier: the Verifier section names the bar and the verifiers that meet it"
U --yes create --verifier > "$OUT/verifier.txt"
g show "understando/verify-wallet:.agents/skills/verify-wallet/features/withdraw.md" > "$OUT/withdraw-2.md"
has "$OUT/withdraw-2.md" "- **Verifiers that meet the bar:**"
has "$OUT/withdraw-2.md" "\`$V\` the overdraft refusal test (contract, rung 3)"
has "$OUT/withdraw-2.md" "- **Verifiers that do not count:**"
has "$OUT/withdraw-2.md" "It is **cannot-fail**: it does not count."
has "$OUT/withdraw-2.md" "\`I2\` (agent-picked, not accepted by the user yet)"
cp "$OUT/withdraw-2.md" "$WORK/feature-sample.md"

step "snippet: a code ref at the head, with its permalink"
U snippet wallet/core.py::withdraw --match "if amount > balance:" > "$OUT/snippet.txt"
has "$OUT/snippet.txt" "wallet/core.py:13-13 at ${HEAD:0:10}"
has "$OUT/snippet.txt" "https://github.com/fixture/wallet/blob/$HEAD/wallet/core.py#L13"
U snippet .agents/skills/verify-wallet/helpers/verify --lines 1-2 > "$OUT/snippet-ready.txt"
has "$OUT/snippet-ready.txt" "(on the understando branch)"

step "export: the data and refs.resolved.json for visual-explainer"
U export --base "$BASE" > "$OUT/export.txt"
X="$RUN/export"
expect "claim strength" "$(field "$X/verify-data.json" "next(c['strength'] for c in d['claims'] if c['id'] == '$CL')")" Proven
expect "invariant authors" "$(field "$X/verify-data.json" "sorted((i['id'], i['author']) for i in d['invariants'] if i['status'] != 'deferred')")" "[('I1', 'user'), ('I2', 'agent')]"
expect "the ref of the check has diff marks" "$(field "$X/refs.resolved.json" "next(r['changes']['added'] != [] for r in d['refs'] if r['path'] == 'tests/test_core.py')")" True
expect "a permalink at the head" "$(field "$X/refs.resolved.json" "all(r['permalink'].startswith('https://github.com/fixture/wallet/blob/') for r in d['refs'])")" True
expect "the control patch" "$(field "$X/refs.resolved.json" "'-    if amount > balance:' in d['controls']['K1'][0]['patch']")" True
expect "the mutation runs" "$(field "$X/verify-data.json" "[m['tool'] for m in d['mutation']]")" "['mutmut', 'cosmic-ray']"

step "export: the no-hand-copy guard refuses pasted code"
cp "$RUN/verify.json" "$OUT/verify.keep.json"
python3 - "$RUN/verify.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
d["claims"][0]["text"] = "if amount > balance:\n        raise OverdraftError(f\"{amount} is above the balance\")"
json.dump(d, open(sys.argv[1], "w"), indent=2)
PY
if U export > "$OUT/export-paste.txt" 2>&1; then fail "export took pasted code"; fi
has "$OUT/export-paste.txt" "pasted code from wallet/core.py:13"
cp "$OUT/verify.keep.json" "$RUN/verify.json"

# ---------------------------------------------------------------------------------------- maintain
step "maintain: a second guard in the CLI; the drive's control no longer fails"
U --yes maintain > "$OUT/maintain-clean.txt"
has "$OUT/maintain-clean.txt" "maintain: clean"
cp "$FIX/later/wallet/cli.py" "$REPO/wallet/cli.py" && g commit -q -am "Refuse an overdraft in the CLI too"
U maintain > "$OUT/maintain-ask.txt"
has "$OUT/maintain-ask.txt" "bash .agents/skills/verify-wallet/helpers/verify prove withdraw"
U --yes maintain > "$OUT/maintain.txt"
cat "$OUT/maintain.txt"
has "$OUT/maintain.txt" "maintain: changed"
has "$OUT/maintain.txt" "FLAG STALE: V1 (the drive of withdraw money): its control K1 no longer makes it fail."
lacks "$OUT/maintain.txt" "FLAG STALE: $V"
test -f "$RUN/maintain/withdraw.md" || fail "maintain wrote no source brief"

step "doctor"
U doctor > "$OUT/doctor.txt" || true
lacks "$OUT/doctor.txt" "Traceback"
lacks "$OUT/doctor.txt" "the store is invalid"

step "the user's checkout and branches"
[ "$(g rev-parse understando/verify-wallet)" != "$TIP" ] || fail "create --verifier did not move the branch"
g merge-base --is-ancestor "$TIP" understando/verify-wallet || fail "the branch was rewritten"
[ "$(g worktree list | wc -l | tr -d ' ')" = 1 ] || fail "a scratch worktree is left in the repo"

step "create on a repo with a verify skill from create-verification-skill: extend it, never a second skill"
R2="$WORK/wallet2"
git clone -q "$REPO" "$R2" && cp -R "$FIX/pstack/." "$R2/"
git -C "$R2" add -A && git -C "$R2" -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false commit -q -m "a pstack verify skill"
"$ROOT/bin/understando" --repo "$R2" --run "$WORK/run2" --yes create --spec "$FIX/create.spec.json" > "$OUT/extend.txt"
has "$OUT/extend.txt" "create: extended .cursor/skills/verify-wallet"
git -C "$R2" ls-tree -r --name-only understando/verify-wallet -- .agents .claude .cursor > "$OUT/tree2.txt"
lacks "$OUT/tree2.txt" ".agents/skills/verify-wallet"
has "$OUT/tree2.txt" ".cursor/skills/verify-wallet/helpers/verify"
git -C "$R2" show "understando/verify-wallet:.cursor/skills/verify-wallet/features/withdraw.md" > "$OUT/withdraw-ext.md"
has "$OUT/withdraw-ext.md" "(written by hand: understando keeps this line)"
has "$OUT/withdraw-ext.md" "## Verifier"
"$ROOT/bin/understando" --repo "$R2" --run "$WORK/run2" create --check > "$OUT/check2.txt"
has "$OUT/check2.txt" "the shape holds."

if [ "${SKIP_FORMAL:-0}" != 1 ]; then
  step "formal: Lean and TLA+ to Formal, the sync into the store, recheck (tests/formal/e2e.sh)"
  bash "$ROOT/tests/formal/e2e.sh"
fi

isolate_compare "$UNDERSTANDO_TEST_ROOT/real-before.sha256"
echo
echo "PASS: understando e2e"
