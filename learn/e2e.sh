#!/usr/bin/env bash
# The learn e2e tests, from one command. No model call.
#
#   learn/e2e.sh            UI build, release binary, Playwright suite, then the fixture smoke run
#   SKIP_SMOKE=1 learn/e2e.sh skip the smoke run
#
# Hermetic: tests/isolate.sh sets the guard (UNDERSTANDO_TEST), the test root, and UNDERSTANDO_HOME and
# UNDERSTANDO_RUNS in it, so ~/.understando (mode.json, runs) is never read or written, and the smoke
# run uses the fixture run, not a real PR run. The real run files keep their sha256.
# The Artifacture runtime is read first from ve_runtime in ~/.understando/config.toml
# (UNDERSTANDO_VE_RUNTIME overrides it) and handed on through the variable.
set -euo pipefail
L="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export E2E_TELEMETRY_DISABLED=1 DO_NOT_TRACK=1
step() { printf '\n== %s\n' "$*"; }
. "$L/../tests/isolate.sh" learn
isolate_snapshot "$UNDERSTANDO_TEST_ROOT/real-before.sha256"
trap 'isolate_cleanup' EXIT
# config.py only reads, so it may read the real config.toml in a test run.
UNDERSTANDO_VE_RUNTIME="${UNDERSTANDO_VE_RUNTIME:-$(UNDERSTANDO_HOME="$ISOLATE_REAL_STORE" python3 "$L/../scripts/config.py" ve-runtime || true)}"
: "${UNDERSTANDO_VE_RUNTIME:?set ve_runtime with understando setup --ve-runtime PATH (or UNDERSTANDO_VE_RUNTIME)}"
export UNDERSTANDO_VE_RUNTIME
step "build the UI"
(cd "$L/web" && { [ -d node_modules ] || npm ci; } && npm run build >/dev/null)
step "build the release binary"
(cd "$L" && cargo build --release --quiet)
step "Playwright: fixture repo, fake claude and fake codex"
(cd "$L/web" && npx playwright test)
if [ "${SKIP_SMOKE:-0}" = 1 ]; then
  echo "skip the smoke run"
else
  step "smoke: understando learn on the fixture run in a temp runs root, model-free"
  bash "$L/web/e2e/smoke.sh"
fi
step "isolation: the real run files have the same sha256 as before the suite"
isolate_compare "$UNDERSTANDO_TEST_ROOT/real-before.sha256"
