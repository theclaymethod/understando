#!/usr/bin/env bash
# The isolation e2e: tests/e2e.sh calls it first, with WORK set. It proves the guard of
# scripts/testguard.py on the real CLI and the real write helpers:
#   - each script imports the guard;
#   - a planted write outside the test root fails with the guard error, and the target stays empty:
#     the run folder of a verb, verify.json (store.save), toolprobe.json, the evidence, also behind
#     an `except Exception`;
#   - a read of the real ~/.understando fails, except in a read-only verb.
# tests/e2e.sh compares the sha256 of the real run files before and after the whole suite.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$ROOT/tests/isolate.sh" isolate
S="$ROOT/scripts"
U="$ROOT/bin/understando"
O="$WORK/isolate"; mkdir -p "$O"
step() { printf '\n== %s\n' "$*"; }
fail() { echo "FAIL: $*"; exit 1; }
has() { grep -qF -- "$2" "$1" || { echo "--- $1"; cat "$1"; fail "$1 lacks: $2"; }; }
# A folder outside the test root, in the system temp folder: a write there is harmless if the guard fails.
OUTSIDE="$(mktemp -d /tmp/understando-guard-outside.XXXXXX)"
trap 'rm -rf "$OUTSIDE"; isolate_cleanup' EXIT
case "$(isolate_resolve "$OUTSIDE")/" in "$UNDERSTANDO_TEST_ROOT"/*) fail "$OUTSIDE is in the test root" ;; esac
empty() { test -z "$(find "$OUTSIDE" -mindepth 1 -print -quit)" || { find "$OUTSIDE"; fail "$1 wrote outside the test root"; }; }

step "guard: each script imports scripts/testguard.py, so each understando process has the guard"
missing="$(cd "$S" && grep -L '^import testguard' $(ls *.py | grep -v '^testguard.py$') || true)"
[ -z "$missing" ] || fail "these scripts do not import testguard: $missing"
echo "$(ls "$S"/*.py | wc -l | tr -d ' ') scripts; each imports the guard"

step "guard: the CLI refuses a planted run-folder write outside the test root"
if "$U" --run "$OUTSIDE/run" --repo "$ROOT" discover status > "$O/cli.txt" 2>&1; then fail "discover wrote outside the test root"; fi
has "$O/cli.txt" "understando test guard: refuse to write $(isolate_resolve "$OUTSIDE")/run"
has "$O/cli.txt" "outside the test root $UNDERSTANDO_TEST_ROOT"
empty "discover"
echo "discover: refused, and the folder outside the root is empty"

step "guard: each write helper refuses a target outside the test root, also behind an except"
python3 - "$S" "$OUTSIDE" "$O" <<'PY'
import os, subprocess, sys
s, outside, out = sys.argv[1:4]
run = os.path.join(outside, "run")
cases = {
    "verify.json (store.save)": f"import store; store.save(store.new('fixture/wallet', 'wallet', 'x'), {outside!r} + '/verify.json')",
    "toolprobe.json": "import toolprobe; toolprobe._store('java', '/x')  # _store hides each OSError",
    "evidence (mkdir)": f"import os, testguard; os.makedirs({outside!r} + '/evidence/V1')",
    "rename (os.replace)": f"import os, testguard; src = {os.environ['UNDERSTANDO_TEST_ROOT']!r} + '/x.json'; open(src, 'w').write('{{}}'); os.replace(src, {outside!r} + '/x.json')",
    "behind except Exception": f"import testguard\ntry:\n    open({outside!r} + '/x.json', 'w')\nexcept Exception:\n    pass\nprint('swallowed')",
}
env = {**os.environ, "UNDERSTANDO_HOME": os.path.join(outside, "uhome")}
for name, code in cases.items():
    r = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {s!r})\n{code}"], env=env, capture_output=True, text=True)
    assert r.returncode == 1, (name, r.returncode, r.stdout, r.stderr)
    assert "understando test guard: refuse to write" in r.stderr and "Traceback" not in r.stderr, (name, r.stderr)
    assert "swallowed" not in r.stdout, name
    assert not os.listdir(outside), (name, os.listdir(outside))
    print(f"refused: {name}")
PY
empty "a write helper"

step "guard: a read of the real ~/.understando fails, except in a read-only verb"
REAL_PROBE="$ISOLATE_REAL_STORE/understando-guard-read-probe/verify.json"
if python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import store; store.load(sys.argv[2])' "$S" "$REAL_PROBE" > "$O/read.txt" 2>&1; then fail "a test read the real store"; fi
has "$O/read.txt" "understando test guard: refuse to read $REAL_PROBE"
"$U" --run "$(dirname "$REAL_PROBE")" --repo "$ROOT" doctor > "$O/doctor-real.txt" 2>&1 || true
if grep -q "understando test guard" "$O/doctor-real.txt"; then cat "$O/doctor-real.txt"; fail "the read-only verb doctor was refused"; fi
test ! -e "$(dirname "$REAL_PROBE")" || fail "doctor made $(dirname "$REAL_PROBE")"
echo "a read: refused; the read-only verb doctor: allowed"

echo
echo "PASS: isolation e2e"
