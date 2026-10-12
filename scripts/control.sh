#!/usr/bin/env bash
# Plant a bug in a throwaway copy of the tree, run a command there, and report red or green.
#
#   scripts/control.sh [--dir DIR] [--expect red|green] --replace PATH OLD NEW -- COMMAND...
#   scripts/control.sh [--dir DIR] [--expect red|green] --patch FILE.diff      -- COMMAND...
#
# DIR (default .) is copied without .git and mutants/. --replace swaps the literal text OLD for NEW
# in PATH; OLD must occur exactly once. --patch applies a unified diff with `patch -p1`.
# COMMAND runs in the copy. The working tree is never written. Exit 0 when the result matches
# --expect (default red), 1 when it does not, 2 on a usage or plant error.
# Gotcha: an editable install points imports at the real tree. Run Python tests as `python -m pytest`
# from the copy, so the copy comes first on sys.path.
set -u

usage() { sed -n '2,/^[^#]/{/^#/!d;s/^# \{0,1\}//;p;}' "$0"; }
DIR=. EXPECT=red MODE= RPATH= OLD= NEW= PATCH=
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --dir) DIR="$2"; shift 2 ;;
    --expect) EXPECT="$2"; shift 2 ;;
    --replace) MODE=replace RPATH="$2" OLD="$3" NEW="$4"; shift 4 ;;
    --patch) MODE=patch PATCH="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"; shift 2 ;;
    --) shift; break ;;
    *) usage >&2; exit 2 ;;
  esac
done
[ -n "$MODE" ] && [ $# -gt 0 ] || { usage >&2; exit 2; }

COPY="$(mktemp -d)/tree"
trap 'rm -rf "$(dirname "$COPY")"' EXIT
rsync -a --exclude .git --exclude mutants "$DIR/" "$COPY/" || exit 2

if [ "$MODE" = replace ]; then
  [ -f "$COPY/$RPATH" ] || { echo "plant error: no file $RPATH" >&2; exit 2; }
  OLD="$OLD" NEW="$NEW" perl -0777 -i -pe '
    BEGIN { $o = $ENV{OLD}; $n = $ENV{NEW} }
    $c = () = /\Q$o\E/g;
    if ($c != 1) { print STDERR "plant error: the text occurs $c times, not once\n"; exit 3 }
    s/\Q$o\E/$n/;' "$COPY/$RPATH" || exit 2
else
  patch -s -p1 -d "$COPY" < "$PATCH" || { echo "plant error: the patch does not apply" >&2; exit 2; }
fi

OUT="$(cd "$COPY" && "$@" 2>&1)"; CODE=$?
[ "$CODE" -eq 0 ] && GOT=green || GOT=red
echo "$GOT: \`$*\` exited $CODE with the planted bug"
printf '%s\n' "$OUT" | tail -n 15 | sed 's/^/  | /'
[ "$GOT" = "$EXPECT" ]
