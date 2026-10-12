#!/usr/bin/env bash
# Run mutmut on the changed functions in a throwaway copy, and print the killed and survived mutants.
#
#   scripts/mutate.sh [--dir DIR] [--base REF] [--tests PATH]           the functions changed since REF
#   scripts/mutate.sh [--dir DIR] [--tests PATH] FILE[::FUNCTION]...    the named files or functions
#
# REF defaults to HEAD, so the default is the uncommitted changes. Name an untracked file as FILE.
# mutmut: $MUTMUT (for example "uv run --with mutmut mutmut" for a project with dependencies), else
# mutmut on PATH, else ~/.understando/tools/mutation/bin/mutmut. When the project has no mutmut
# config, the copy gets one: source_paths = the top folders of the files, tests = PATH (default tests/).
# Prints one line for each mutant, the diff of each survivor, and a summary line. Review each
# survivor: harmless (the same behavior) or a real gap (write a test that kills it).
# The working tree is never written. Exit 0 when mutmut ran, 2 when it could not.
set -u

usage() { sed -n '2,/^[^#]/{/^#/!d;s/^# \{0,1\}//;p;}' "$0"; }
DIR=. BASE=HEAD TESTS=tests/
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --dir) DIR="$2"; shift 2 ;;
    --base) BASE="$2"; shift 2 ;;
    --tests) TESTS="$2"; shift 2 ;;
    -*) usage >&2; exit 2 ;;
    *) break ;;
  esac
done
cd "$DIR" || exit 2

if [ -n "${MUTMUT:-}" ]; then read -ra MM <<< "$MUTMUT"
elif command -v mutmut >/dev/null; then MM=(mutmut)
elif [ -x "$HOME/.understando/tools/mutation/bin/mutmut" ]; then MM=("$HOME/.understando/tools/mutation/bin/mutmut")
else echo "missing: mutmut (run scripts/setup.sh)" >&2; exit 2; fi

# The mutmut name of the function that holds each of the given lines: x_f, or xǁClassǁmethod.
functions_at() { # FILE "LINE LINE ..."
  awk -v lines="$2" '
    BEGIN { n = split(lines, L, " "); for (i = 1; i <= n; i++) want[L[i]] = 1 }
    /^class [A-Za-z_]/ { s = $0; sub(/^class[ \t]+/, "", s); sub(/[^A-Za-z0-9_].*/, "", s); cls = s; cur = ""; mind = "" }
    /^[ \t]*(async[ \t]+)?def[ \t]/ {
      ind = match($0, /[^ \t]/) - 1; s = $0; sub(/^[ \t]*(async[ \t]+)?def[ \t]+/, "", s); sub(/[^A-Za-z0-9_].*/, "", s)
      if (ind == 0) { cur = "x_" s; cls = "" }
      else if (cls != "" && (mind == "" || ind == mind)) { mind = ind; cur = "xǁ" cls "ǁ" s }
    }
    /^[^] \t#@)}]/ && !/^(class|def|async)[ \t]/ { cur = ""; cls = "" }
    (NR in want) && cur != "" && !(cur in seen) { seen[cur] = 1; print cur }
  ' "$1"
}
module_of() { local m="${1%.py}"; m="${m#src/}"; echo "${m//\//.}"; }

PATTERNS=() FILES=()
if [ $# -gt 0 ]; then
  for t in "$@"; do
    f="${t%%::*}"; FILES+=("$f")
    if [ "$t" = "$f" ]; then PATTERNS+=("$(module_of "$f").*"); else PATTERNS+=("$(module_of "$f").x_${t#*::}__mutmut_*"); fi
  done
else
  while IFS= read -r f; do
    lines="$(git diff -U0 "$BASE" -- "$f" | sed -nE 's/^@@ [^+]*\+([0-9]+)(,([0-9]+))? @@.*/\1 \3/p' |
      awk '{ c = ($2 == "") ? 1 : $2; if (c == 0) c = 1; for (i = 0; i < c; i++) printf "%d ", $1 + i }')"
    for fn in $(functions_at "$f" "$lines"); do FILES+=("$f"); PATTERNS+=("$(module_of "$f").${fn}__mutmut_*"); done
  done < <(git diff --name-only --diff-filter=AM "$BASE" -- '*.py')
fi
[ ${#PATTERNS[@]} -gt 0 ] || { echo "no changed Python functions since $BASE"; exit 0; }

COPY="$(mktemp -d)/tree"
trap 'rm -rf "$(dirname "$COPY")"' EXIT
rsync -a --exclude .git --exclude mutants . "$COPY/" || exit 2
cd "$COPY" || exit 2
if ! grep -qs '^\[tool\.mutmut\]' pyproject.toml && ! grep -qs '^\[mutmut\]' setup.cfg; then
  { echo; echo "[mutmut]"; echo "source_paths ="; printf '%s\n' "${FILES[@]}" | sed 's|/.*||' | sort -u | sed 's/^/    /'
    echo "pytest_add_cli_args_test_selection ="; echo "    $TESTS"; } >> setup.cfg
fi

RUN="$(env -u PYTHONPATH "${MM[@]}" run "${PATTERNS[@]}" 2>&1)"
RES="$(env -u PYTHONPATH "${MM[@]}" results --all true 2>/dev/null)"
K=0 S=0 O=0 SURVIVORS=()
while IFS= read -r line; do
  name="${line%%: *}"; name="${name#"${name%%[! ]*}"}"; status="${line##*: }"
  hit=; for p in "${PATTERNS[@]}"; do [[ "$name" == $p ]] && hit=1; done
  [ -n "$hit" ] || continue
  echo "$status: $name"
  case "$status" in killed) K=$((K + 1)) ;; survived) S=$((S + 1)); SURVIVORS+=("$name") ;; *) O=$((O + 1)) ;; esac
done <<< "$RES"
[ $((K + S + O)) -gt 0 ] || { echo "mutmut produced no results:"; printf '%s\n' "$RUN" | tail -n 15; exit 2; }
for name in ${SURVIVORS[@]+"${SURVIVORS[@]}"}; do
  echo "--- survived: $name"; env -u PYTHONPATH "${MM[@]}" show "$name" 2>&1 | sed '1d; s/^/  | /'
done
echo "summary: killed $K, survived $S, other $O"
