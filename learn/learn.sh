#!/usr/bin/env bash
# understando learn: start the learn app for one run folder and open the browser.
#
#   learn/learn.sh <run-dir> [--repo <git repo>] [--env-file FILE] [--port N] [--no-open]
#
# --repo is the local clone of the reviewed repo; it must hold the PR head commit. The default
# for Function-Health/function-intelligence is ~/dev/function-intelligence. --env-file defaults
# to learn/hermetic-env.sh. The script builds the binary and the UI only when they are missing,
# and it compiles the chapters when they are older than the chapter MDX.
set -euo pipefail
L="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="${1:?usage: learn.sh <run-dir> [--repo DIR] [--env-file FILE] [--port N] [--no-open]}"
shift
RUN="$(cd "$RUN" && pwd)"
REPO="" ENV_FILE="$L/hermetic-env.sh" PASS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --port) PASS+=(--port "$2"); shift 2 ;;
    --no-open) PASS+=(--no-open); shift ;;
    *) echo "learn.sh: unknown option $1" >&2; exit 2 ;;
  esac
done
if [ -z "$REPO" ]; then
  NAME="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["repo"].lower())' "$RUN/trust-map.json")"
  case "$NAME" in
    function-health/function-intelligence) REPO="$HOME/dev/function-intelligence" ;;
    *) echo "learn.sh: pass --repo <local clone of $NAME>" >&2; exit 2 ;;
  esac
fi
# The secret_paths of the per-repo understando.toml join the tutor sandbox's read-deny list.
UNDERSTANDO_DENY_EXTRA="$(python3 "$L/../scripts/config.py" deny-globs --repo "$REPO" 2>/dev/null || true)"
export UNDERSTANDO_DENY_EXTRA
BIN="${UNDERSTANDO_LEARN_BIN:-$L/target/release/understando-learn}"
if [ ! -x "$BIN" ]; then
  [ -f "$L/web/dist/index.html" ] || { (cd "$L/web" && { [ -d node_modules ] || npm ci; } && npm run build); }
  (cd "$L" && cargo build --release)
fi
CH="$RUN/learn/chapters.json"
if command -v node >/dev/null && [ -d "$L/web/node_modules" ]; then
  if [ ! -f "$CH" ] || [ -n "$(find "$RUN/explainer.mdx" "$RUN/chapters" -newer "$CH" -print -quit 2>/dev/null)" ]; then
    node "$L/web/scripts/compile-chapters.mjs" "$RUN"
  fi
fi
exec "$BIN" "$RUN" --repo "$REPO" --env-file "$ENV_FILE" ${PASS[@]+"${PASS[@]}"}
