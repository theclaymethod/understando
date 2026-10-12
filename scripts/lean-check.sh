#!/usr/bin/env bash
# Build a Lean project, then check that each named theorem uses only the standard axioms and no sorry.
#
#   scripts/lean-check.sh [--dir DIR] --import MODULE THEOREM...
#
# Runs `lake build` in DIR (default .), then `lake env lean` on a scratch file that holds
# `import MODULE` and `#print axioms THEOREM` for each theorem. Fails on a build error, on `sorry`,
# `admit` or a new `axiom` in a source file, and on any axiom other than propext, Classical.choice
# and Quot.sound. Prints one ok line for each theorem. Exit 0 only when every check holds.
set -u

usage() { sed -n '2,/^[^#]/{/^#/!d;s/^# \{0,1\}//;p;}' "$0"; }
DIR=. MOD=
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --dir) DIR="$2"; shift 2 ;;
    --import) MOD="$2"; shift 2 ;;
    -*) usage >&2; exit 2 ;;
    *) break ;;
  esac
done
[ -n "$MOD" ] && [ $# -gt 0 ] || { usage >&2; exit 2; }
command -v lake >/dev/null || { echo "missing: lake (run scripts/setup.sh)" >&2; exit 2; }
cd "$DIR" || exit 2

BUILD="$(lake build 2>&1)" || { printf "%s\n" "$BUILD" | tail -n 20; echo "red: lake build failed"; exit 1; }
echo "ok: lake build"

HITS="$(grep -rnE '\bsorry\b|\badmit\b|^axiom ' --include='*.lean' --exclude-dir=.lake . || true)"
[ -z "$HITS" ] || { echo "red: the source holds sorry, admit or axiom:"; echo "$HITS"; exit 1; }

SCRATCH="$(mktemp -d)/Axioms.lean"
trap 'rm -rf "$(dirname "$SCRATCH")"' EXIT
{ echo "import $MOD"; for t in "$@"; do echo "#print axioms $t"; done; } > "$SCRATCH"
OUT="$(lake env lean "$SCRATCH" 2>&1)" || { echo "red: #print axioms failed:"; echo "$OUT"; exit 1; }
FLAT="$(printf '%s' "$OUT" | tr '\n' ' ' | tr -s ' ')"

RC=0
for t in "$@"; do
  short="${t##*.}"
  if printf '%s' "$FLAT" | grep -qE "'[^']*$short' does not depend on any axioms"; then echo "ok: $t uses no axioms"; continue; fi
  ax="$(printf '%s' "$FLAT" | grep -oE "'[^']*$short' depends on axioms: \[[^]]*\]" | head -1 | sed 's/.*\[//; s/\]//')"
  [ -n "$ax" ] || { echo "red: no axiom report for $t"; RC=1; continue; }
  extra="$(printf '%s' "$ax" | tr ',' '\n' | tr -d ' ' | grep -vxE 'propext|Classical\.choice|Quot\.sound' || true)"
  if [ -n "$extra" ]; then echo "red: $t depends on $(echo $extra)"; RC=1; else echo "ok: $t axioms [$ax]"; fi
done
exit "$RC"
