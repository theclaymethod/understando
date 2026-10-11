# The test isolation. Each test script sources this file at the top, before any understando call:
#
#   . "$ROOT/tests/isolate.sh" NAME        (then isolate_selfcheck runs at once)
#
# - UNDERSTANDO_TEST=1 turns on the guard in each understando Python process (scripts/testguard.py):
#   a write outside UNDERSTANDO_TEST_ROOT stops the process with "understando test guard: ...".
# - UNDERSTANDO_TEST_ROOT is a `mktemp -d` folder. A nested script (tests/e2e.sh calls the others)
#   keeps the root of its caller, because it writes in the work folder of its caller.
# - UNDERSTANDO_HOME and UNDERSTANDO_RUNS go under the script's own `mktemp -d` folder in the root.
# - TMPDIR goes under the root, so the temp files of Python, node and git stay in it.
# isolate_selfcheck fails the suite when one of the three resolves under the real ~/.understando.
# isolate_snapshot and isolate_compare record the sha256 of the real run files, before and after.

isolate_fail() { echo "FAIL: isolation: $*" >&2; exit 1; }
isolate_real() { python3 -c 'import os, pwd; print(os.path.realpath(os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".understando")))'; }
isolate_resolve() { python3 -c 'import os, sys; print(os.path.realpath(os.path.expanduser(sys.argv[1])))' "$1"; }
isolate_under() { case "$1/" in "$2"/*) return 0 ;; *) return 1 ;; esac; }

ISOLATE_NAME="${1:-test}"
ISOLATE_REAL_STORE="$(isolate_real)"
export PYTHONDONTWRITEBYTECODE=1
if [ -z "${UNDERSTANDO_TEST_ROOT:-}" ]; then
  UNDERSTANDO_TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/understando-test.XXXXXX")"
  ISOLATE_OWNS_ROOT=1
else
  ISOLATE_OWNS_ROOT=0
fi
UNDERSTANDO_TEST_ROOT="$(isolate_resolve "$UNDERSTANDO_TEST_ROOT")"
export UNDERSTANDO_TEST=1 UNDERSTANDO_TEST_ROOT
mkdir -p "$UNDERSTANDO_TEST_ROOT/tmp"
export TMPDIR="$UNDERSTANDO_TEST_ROOT/tmp"
ISOLATE_DIR="$(mktemp -d "$UNDERSTANDO_TEST_ROOT/$ISOLATE_NAME.XXXXXX")"
export UNDERSTANDO_HOME="$ISOLATE_DIR/uhome" UNDERSTANDO_RUNS="$ISOLATE_DIR/runs"
mkdir -p "$UNDERSTANDO_HOME" "$UNDERSTANDO_RUNS"

# The effective values: an unset UNDERSTANDO_HOME is $HOME/.understando, an unset UNDERSTANDO_RUNS is
# $UNDERSTANDO_HOME/runs. Each must be in the test root, and none may be in the real ~/.understando.
isolate_selfcheck() {
  [ -n "${UNDERSTANDO_TEST_ROOT:-}" ] || isolate_fail "UNDERSTANDO_TEST_ROOT is not set"
  [ "${UNDERSTANDO_TEST:-}" = 1 ] || isolate_fail "UNDERSTANDO_TEST is not 1"
  local root home runs name value
  root="$(isolate_resolve "$UNDERSTANDO_TEST_ROOT")"
  home="$(isolate_resolve "${UNDERSTANDO_HOME:-$HOME/.understando}")"
  runs="$(isolate_resolve "${UNDERSTANDO_RUNS:-$home/runs}")"
  for name in root home runs; do
    value="${!name}"
    if [ "$value" = "$ISOLATE_REAL_STORE" ] || isolate_under "$value" "$ISOLATE_REAL_STORE" || isolate_under "$ISOLATE_REAL_STORE" "$value"; then
      isolate_fail "the test $name $value is the real $ISOLATE_REAL_STORE, or holds it, or is in it"
    fi
  done
  isolate_under "$home" "$root" || isolate_fail "UNDERSTANDO_HOME $home is not in the test root $root"
  isolate_under "$runs" "$root" || isolate_fail "UNDERSTANDO_RUNS $runs is not in the test root $root"
  echo "isolation ($ISOLATE_NAME): root $root; home and runs are in it; the real store $ISOLATE_REAL_STORE is not"
}

# The real files that a test must never change: the #489 run (UNDERSTANDO_GUARD_WATCH overrides it,
# a colon-separated list) and the machine state files. A missing path is skipped. shots/ is left out:
# it holds screenshots that other sessions take of the page, not run state.
isolate_watch() {
  local w="${UNDERSTANDO_GUARD_WATCH:-$ISOLATE_REAL_STORE/runs/function-intelligence/489}"
  local IFS=:
  for p in $w "$ISOLATE_REAL_STORE/mode.json" "$ISOLATE_REAL_STORE/config.toml" "$ISOLATE_REAL_STORE/toolprobe.json"; do
    [ -e "$p" ] && find "$p" -type f -not -path '*/shots/*'
  done | LC_ALL=C sort
}
isolate_snapshot() {  # isolate_snapshot FILE: one "sha256  path" line for each watched real file
  isolate_watch | while IFS= read -r f; do shasum -a 256 "$f"; done > "$1"
}
isolate_compare() {  # isolate_compare BEFORE: fail when a watched real file is new, gone or changed
  local after="$1.after"
  isolate_snapshot "$after"
  if ! diff "$1" "$after" > "$1.diff"; then
    echo "--- the real files that changed during the suite:" >&2
    grep '^[<>]' "$1.diff" | sed -E 's/^[<>] [0-9a-f]+  //' | LC_ALL=C sort -u >&2
    isolate_fail "a real file changed while the suite ran (another session can change it too: check the list)"
  fi
  echo "the real files are unchanged: $(wc -l < "$1" | tr -d ' ') files, the same sha256 before and after"
}
isolate_cleanup() { if [ "$ISOLATE_OWNS_ROOT" = 1 ] && [ "${KEEP:-0}" != 1 ]; then rm -rf "$UNDERSTANDO_TEST_ROOT"; fi; }

isolate_selfcheck
