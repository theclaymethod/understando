#!/usr/bin/env bash
# The one e2e check of understando. It needs no model. A step whose tool is missing prints SKIP.
#
#   tests/check.sh
#
# It checks the frontmatter, every relative link, each script's --help, setup.sh in a fake HOME,
# control.sh (red on a planted bug, the tree untouched), mutate.sh (a killed and a survived mutant),
# and lean-check.sh and tlc.sh on the tiny fixtures, each with a planted wrong model.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$ROOT/scripts" FIX="$ROOT/tests/fixture"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
FAILED=0
pass() { echo "PASS $*"; }
fail() { echo "FAIL $*"; FAILED=1; }
skip() { echo "SKIP $*"; }

# 1. The frontmatter parses, and the description is the agreed one.
WANT="Verifier-driven development and formal verification: state invariants, write checks that are proven to fail on planted bugs, Lean/TLA+ proofs with conformance, mutation testing. Use for 'prove this', 'can this test fail', 'formal methods', 'build this verifier-first'."
FM="$(awk 'NR == 1 && $0 != "---" { exit 1 } NR > 1 && $0 == "---" { exit } NR > 1 { print }' "$ROOT/SKILL.md")"
NAME="$(printf '%s\n' "$FM" | sed -n 's/^name: //p')"
DESC="$(printf '%s\n' "$FM" | sed -n 's/^description: "\(.*\)"$/\1/p')"
[ "$NAME" = understando ] && [ "$DESC" = "$WANT" ] && pass "frontmatter" || fail "frontmatter: name '$NAME', description '$DESC'"

# 2. Every relative link in SKILL.md, modes/ and references/ resolves.
BAD=0
for f in "$ROOT/SKILL.md" "$ROOT"/modes/*.md "$ROOT"/references/*.md; do
  for link in $(grep -oE '\]\([^)]+\)' "$f" | sed 's/^](//; s/)$//; s/#.*//' | grep -vE '^(https?:|mailto:|$)'); do
    [ -e "$(dirname "$f")/$link" ] || { fail "link $link in ${f#$ROOT/}"; BAD=1; }
  done
done
[ "$BAD" = 0 ] && pass "links"

# 3. Each script prints its use.
for sc in "$S"/*.sh; do
  "$sc" --help 2>&1 | grep -q . && pass "--help ${sc#$ROOT/}" || fail "--help ${sc#$ROOT/}"
done

# 4. setup.sh in a fake HOME: the links, twice; then --check changes nothing.
H="$T/home"; mkdir -p "$H"
HOME="$H" "$S/setup.sh" --links-only > "$T/s1" 2>&1
HOME="$H" "$S/setup.sh" --links-only > "$T/s2" 2>&1
LINKS=0; for d in .agents .claude .codex .cursor; do [ "$(readlink "$H/$d/skills/understando")" = "$ROOT" ] && LINKS=$((LINKS + 1)); done
[ "$LINKS" = 4 ] && [ "$(grep -c '^made:' "$T/s1")" = 4 ] && ! grep -qv '^ok:' "$T/s2" \
  && pass "setup.sh links, idempotent" || fail "setup.sh links: $(cat "$T/s1" "$T/s2")"
HOME="$H" "$S/setup.sh" --check > "$T/s3" 2>&1
[ ! -e "$H/.understando" ] && grep -q 'TLC' "$T/s3" && pass "setup.sh --check changes nothing" || fail "setup.sh --check: $(cat "$T/s3")"

# 5. control.sh goes red on a planted bug and leaves the tree untouched.
if command -v python3 >/dev/null && python3 -c 'import pytest' 2>/dev/null; then
  BEFORE="$(cd "$FIX/py" && find . -type f -not -path '*/__pycache__/*' -exec shasum {} + | sort)"
  "$S/control.sh" --dir "$FIX/py" --replace wallet/core.py 'balance - amount' 'balance + amount' -- python3 -m pytest -q -p no:cacheprovider > "$T/c1" 2>&1 \
    && grep -q '^red:' "$T/c1" && pass "control.sh red on a planted bug" || fail "control.sh red: $(cat "$T/c1")"
  "$S/control.sh" --dir "$FIX/py" --replace wallet/core.py 'raise ValueError("overdraft")' 'raise ValueError("x")' -- python3 -m pytest -q -p no:cacheprovider > "$T/c2" 2>&1
  [ $? = 1 ] && grep -q '^green:' "$T/c2" && pass "control.sh green on a bug the test cannot see" || fail "control.sh green: $(cat "$T/c2")"
  AFTER="$(cd "$FIX/py" && find . -type f -not -path '*/__pycache__/*' -exec shasum {} + | sort)"
  [ "$BEFORE" = "$AFTER" ] && pass "control.sh left the tree untouched" || fail "control.sh changed the tree"
else skip "control.sh: python3 with pytest is not installed"; fi

# 6. mutate.sh kills one mutant and lets one survive.
if "$S/mutate.sh" --dir "$FIX/py" wallet/core.py::withdraw > "$T/m" 2>&1; then
  grep -q '^killed: wallet.core.x_withdraw__mutmut_' "$T/m" && grep -q '^survived: wallet.core.x_withdraw__mutmut_' "$T/m" \
    && pass "mutate.sh: $(grep '^summary' "$T/m")" || fail "mutate.sh: $(cat "$T/m")"
elif grep -q '^missing' "$T/m"; then skip "mutate.sh: $(cat "$T/m")"; else fail "mutate.sh: $(cat "$T/m")"; fi

# 7. lean-check.sh proves the fixture theorem; a planted wrong model breaks it.
TC="$(elan toolchain list 2>/dev/null | grep -m1 -o '^leanprover[^ ]*')"
if command -v lake >/dev/null && [ -n "$TC" ]; then
  cp -R "$FIX/lean" "$T/lean" && echo "$TC" > "$T/lean/lean-toolchain"
  "$S/lean-check.sh" --dir "$T/lean" --import Fixture withdraw_nonneg > "$T/l1" 2>&1 && grep -q '^ok: withdraw_nonneg axioms' "$T/l1" \
    && pass "lean-check.sh" || fail "lean-check.sh: $(cat "$T/l1")"
  "$S/control.sh" --dir "$T/lean" --replace Fixture.lean 'balance - amount' 'balance - amount - 1' -- "$S/lean-check.sh" --import Fixture withdraw_nonneg > "$T/l2" 2>&1 \
    && pass "lean-check.sh red on a wrong model" || fail "lean-check.sh control: $(cat "$T/l2")"
else skip "lean-check.sh: no lake or no Lean toolchain (run scripts/setup.sh)"; fi

# 8. tlc.sh checks the fixture spec; a planted wrong spec violates the invariant.
"$S/tlc.sh" "$FIX/tla/Counter.tla" > "$T/t1" 2>&1; CODE=$?
if [ "$CODE" = 2 ] && grep -q '^missing' "$T/t1"; then skip "tlc.sh: $(cat "$T/t1")"
else
  [ "$CODE" = 0 ] && pass "tlc.sh" || fail "tlc.sh exited $CODE: $(tail -5 "$T/t1")"
  "$S/control.sh" --dir "$FIX/tla" --replace Counter.tla 'n < Max' 'n <= Max' -- "$S/tlc.sh" Counter.tla > "$T/t2" 2>&1 \
    && grep -q 'exited 12' "$T/t2" && pass "tlc.sh red on a wrong spec" || fail "tlc.sh control: $(cat "$T/t2")"
fi

[ "$FAILED" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit "$FAILED"
