#!/usr/bin/env bash
# Run TLC on a TLA+ spec and its cfg, with the jar and Java found for you.
#
#   scripts/tlc.sh SPEC.tla [CFG] [-- TLC FLAGS...]
#
# CFG defaults to SPEC.cfg. Java: $JAVA_HOME, then Homebrew openjdk, then java on PATH.
# Jar: $TLA2TOOLS, else ~/.understando/tools/tla2tools.jar (scripts/setup.sh installs both).
# Add `-- -dump states.txt` to keep every reachable state for a replay through the real code.
# Exit: TLC's code. 0 = no error, 11 = deadlock, 12 = a safety violation, 13 = a liveness violation.
set -u

usage() { sed -n '2,/^[^#]/{/^#/!d;s/^# \{0,1\}//;p;}' "$0"; }
case "${1:-}" in -h|--help) usage; exit 0 ;; ""|--) usage >&2; exit 2 ;; esac
SPEC="$1"; shift
CFG="${SPEC%.tla}.cfg"
if [ $# -gt 0 ] && [ "$1" != -- ]; then CFG="$1"; shift; fi
[ "${1:-}" = -- ] && shift

JAVA=
for j in "${JAVA_HOME:-/nonexistent}/bin/java" "$(brew --prefix openjdk 2>/dev/null)/bin/java" "$(command -v java)"; do
  [ -x "$j" ] && "$j" -version >/dev/null 2>&1 && { JAVA="$j"; break; }
done
JAR="${TLA2TOOLS:-$HOME/.understando/tools/tla2tools.jar}"
[ -n "$JAVA" ] || { echo "missing: Java (run scripts/setup.sh)" >&2; exit 2; }
[ -s "$JAR" ] || { echo "missing: $JAR (run scripts/setup.sh)" >&2; exit 2; }

META="$(mktemp -d)"
trap 'rm -rf "$META"' EXIT
[ -f "$CFG" ] || { echo "missing: the cfg $CFG" >&2; exit 2; }
CFG="$(cd "$(dirname "$CFG")" && pwd)/$(basename "$CFG")"
cd "$(dirname "$SPEC")" || exit 2
"$JAVA" -XX:+UseParallelGC -cp "$JAR" tlc2.TLC -workers auto -metadir "$META" -cleanup \
  -config "$CFG" "$@" "$(basename "$SPEC")"
