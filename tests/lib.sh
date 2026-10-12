# The shell helpers of the e2e scripts (tests/e2e.sh, tests/isolate-e2e.sh, tests/formal/e2e.sh).
# Source it after tests/isolate.sh. g needs REPO, and cleanup needs WORK.

step() { printf '\n== %s\n' "$*"; }
fail() { echo "FAIL: $*"; exit 1; }
has() { grep -qF -- "$2" "$1" || { echo "--- $1"; cat "$1"; fail "$1 lacks: $2"; }; }
lacks() { if grep -qF -- "$2" "$1"; then echo "--- $1"; cat "$1"; fail "$1 has: $2"; fi; }
expect() { [ "$2" = "$3" ] || fail "$1: expected '$3', got '$2'"; echo "ok: $1 = $2"; }
g() { git -C "$REPO" -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false "$@"; }
cleanup() { if [ "${KEEP:-0}" = 1 ]; then echo "kept $WORK"; else rm -rf "$WORK"; fi; isolate_cleanup; }

# field FILE EXPR...: each Python expression over the JSON of FILE (as d), one line each, in one
# Python process. fields FILE EXPR... puts the lines into the array F.
field() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print('\n'.join(str(eval(e, {'d': d})) for e in sys.argv[2:]))" "$@"; }
fields() {
  F=()
  local line
  while IFS= read -r line; do F+=("$line"); done < <(field "$@")
  [ "${#F[@]}" = "$(($# - 1))" ] || fail "field $1: expected $(($# - 1)) values, got ${#F[@]}"
}
