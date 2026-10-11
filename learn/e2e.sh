#!/usr/bin/env bash
# The learn e2e tests, from one command. No model call.
#
#   learn/e2e.sh            UI build, release binary, Playwright suite, then the #489 smoke run
#   SKIP_489=1 learn/e2e.sh skip the #489 smoke run
#
# The Artifacture runtime is ve_runtime in ~/.understando/config.toml (UNDERSTANDO_VE_RUNTIME overrides it).
set -euo pipefail
L="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export E2E_TELEMETRY_DISABLED=1 DO_NOT_TRACK=1
step() { printf '\n== %s\n' "$*"; }
UNDERSTANDO_VE_RUNTIME="${UNDERSTANDO_VE_RUNTIME:-$(python3 "$L/../scripts/config.py" ve-runtime || true)}"
: "${UNDERSTANDO_VE_RUNTIME:?set ve_runtime with understando setup --ve-runtime PATH (or UNDERSTANDO_VE_RUNTIME)}"
export UNDERSTANDO_VE_RUNTIME
step "build the UI"
(cd "$L/web" && { [ -d node_modules ] || npm ci; } && npm run build >/dev/null)
step "build the release binary"
(cd "$L" && cargo build --release --quiet)
step "Playwright: fixture repo, fake claude and fake codex"
(cd "$L/web" && npx playwright test)
if [ "${SKIP_489:-0}" = 1 ]; then echo "skip the #489 smoke run"; exit 0; fi
step "smoke: understando learn on <runs root>/function-intelligence/489, model-free"
bash "$L/web/e2e/smoke-489.sh"
