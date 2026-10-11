#!/usr/bin/env bash
# The isolation e2e: tests/e2e.sh calls it first, with WORK set. It proves the guard of
# scripts/testguard.py on the real CLI and the real write helpers:
#   - each script imports the guard;
#   - a planted write outside the test root fails with the guard error, and the target stays empty:
#     the journal, mode.json, toolprobe.json, config.toml, trust-map.json (tm.save), ci.json and
#     review.json, also behind an `except Exception`;
#   - a read of the real ~/.understando fails, except in a read-only verb;
#   - out of a test run, review refuses a real run folder when the gh on PATH is a fake one.
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

step "guard: the CLI refuses a planted journal write outside the test root"
if "$U" --run "$OUTSIDE/run" note decision "a planted write" > "$O/note.txt" 2>&1; then fail "note wrote outside the test root"; fi
has "$O/note.txt" "understando test guard: refuse to write $(isolate_resolve "$OUTSIDE")/run"
has "$O/note.txt" "outside the test root $UNDERSTANDO_TEST_ROOT"
empty "note"
echo "note: refused, and the folder outside the root is empty"

step "guard: each write helper refuses a target outside the test root, also behind an except"
python3 - "$S" "$OUTSIDE" "$O" <<'PY'
import os, subprocess, sys
s, outside, out = sys.argv[1:4]
run = os.path.join(outside, "run")
cases = {
    "mode.json (ctx.save_mode)": "import ctx; ctx.save_mode({'on': True})",
    "toolprobe.json": "import toolprobe; toolprobe._store('java', '/x')  # _store hides each OSError",
    "config.toml (config.save_global)": "import config; config.save_global({'ve_runtime': '/x'})",
    "journal (journal.append)": f"import journal, pathlib; journal.append(pathlib.Path({run!r}) / 'journal.jsonl', 'decision', 'x')",
    "trust-map.json (tm.save)": f"import tm; tm.save({{'schema_version': 1}}, {outside!r} + '/trust-map.json')",
    "ci.json (write_text)": f"import pathlib, testguard; pathlib.Path({outside!r}, 'ci.json').write_text('{{}}')",
    "review.json (os.replace)": f"import os, testguard; src = {os.environ['UNDERSTANDO_TEST_ROOT']!r} + '/review.json'; open(src, 'w').write('{{}}'); os.replace(src, {outside!r} + '/review.json')",
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
REAL_PROBE="$ISOLATE_REAL_STORE/understando-guard-read-probe/trust-map.json"
if python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import tm; tm.load(sys.argv[2])' "$S" "$REAL_PROBE" > "$O/read.txt" 2>&1; then fail "a test read the real store"; fi
has "$O/read.txt" "understando test guard: refuse to read $REAL_PROBE"
"$U" --run "$(dirname "$REAL_PROBE")" --json signals > "$O/signals-real.json" 2> "$O/signals-real.err" || true
if grep -q "understando test guard" "$O/signals-real.json" "$O/signals-real.err"; then cat "$O/signals-real.err"; fail "the read-only verb signals was refused"; fi
test ! -e "$(dirname "$REAL_PROBE")" || fail "signals made $(dirname "$REAL_PROBE")"
echo "a read: refused; the read-only verb signals: allowed"

step "fake gh: out of a test run, review refuses a real run folder when the gh on PATH is a fake"
FG="$WORK/fake-gh"; mkdir -p "$FG/bin"
cat > "$FG/bin/gh" <<'GH'
#!/usr/bin/env bash
printf '{"headRefOid":"%s","baseRefName":"main","headRefName":"x","state":"OPEN","title":"x"}\n' 0123456789012345678901234567890123456789
GH
chmod +x "$FG/bin/gh"
git init -q "$FG/wallet"
git -C "$FG/wallet" remote add origin https://github.com/fixture/wallet.git
# /understando-guard-absent cannot be made (the root folder is read-only), so a failed guard writes nothing.
NOT_TEMP="/understando-guard-absent/runs"
(cd "$FG/wallet" && env -u UNDERSTANDO_TEST PATH="$FG/bin:$PATH" UNDERSTANDO_RUNS="$NOT_TEMP" "$U" review 7) > "$O/fake-gh.txt" 2>&1 && fail "review ran with a fake gh"
has "$O/fake-gh.txt" "refuse: the gh on PATH is $FG/bin/gh"
has "$O/fake-gh.txt" "a fake gh in a temp folder"
has "$O/fake-gh.txt" "the real run folder $NOT_TEMP/wallet/7"
test ! -e "$UNDERSTANDO_HOME/mode.json" || fail "review turned the mode on before the refusal"
env -u UNDERSTANDO_TEST PATH="$FG/bin:$PATH" python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import testguard; assert testguard.fake_gh_refusal(sys.argv[2]) is None' "$S" "$WORK/runs/wallet/7" \
  || fail "the fake-gh check refused a run folder in a temp folder"
echo "review: refused with the fake gh named; a temp run folder is allowed"

echo
echo "PASS: isolation e2e"
