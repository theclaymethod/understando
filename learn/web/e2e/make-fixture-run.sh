#!/usr/bin/env bash
# Build the understando fixture as a run folder for the learn e2e tests.
#
#   learn/web/e2e/make-fixture-run.sh <work dir>
#
# Writes <work>/repo (a git repo: base commit, then the PR commit) and <work>/run (the run
# folder: trust-map.json with the learn exercises, explainer.mdx, chapters/, learn/chapters.json).
# No model call. The steps are those of tests/e2e.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
FIX="$ROOT/tests/fixture"
S="$ROOT/scripts"
WORK="$1"
REPO="$WORK/repo"
RUN="$WORK/run"
MAP="$RUN/trust-map.json"
mkdir -p "$REPO" "$RUN"
g() { git -C "$REPO" -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false "$@"; }
cp -R "$FIX/base/." "$REPO/"
g init -q -b main
g add -A && g commit -q -m "base"
BASE="$(g rev-parse HEAD)"
cp -R "$FIX/head/." "$REPO/"
g add -A && g commit -q -m "Refuse overdrafts in the wallet"
HEAD="$(g rev-parse HEAD)"
sed -e "s/BASE_SHA/$BASE/" -e "s/HEAD_SHA/$HEAD/" "$FIX/inventory.json" > "$MAP"
python3 "$S/scan.py" --repo "$REPO" --base "$BASE" --head "$HEAD" --src-prefix wallet/ --test-prefix tests/ --add "$MAP" >/dev/null
python3 - "$MAP" "$FIX/plain.json" "$ROOT/learn/web/e2e/fixtures/exercises.json" "$FIX/promises.json" <<'PY'
import json, sys
data, plain, exercises, promises = (json.load(open(p)) for p in sys.argv[1:5])
for claim in data["claims"]:
    if "plain" not in claim and claim["id"] in plain:
        claim["plain"] = plain[claim["id"]]
data["exercises"] = exercises
data["promises"] = promises
json.dump(data, open(sys.argv[1], "w"), indent=2)
PY
python3 "$S/run_control.py" --map "$MAP" --repo "$REPO" --baseline --scratch "$WORK/scratch" >/dev/null
python3 "$S/run_control.py" --map "$MAP" --repo "$REPO" --all --scratch "$WORK/scratch" >/dev/null
python3 "$S/mechanical.py" --map "$MAP" --repo "$REPO" >/dev/null
python3 "$S/verdicts.py" "$MAP" >/dev/null
python3 "$S/validate.py" "$MAP"
python3 "$S/explain.py" --map "$MAP" --repo "$REPO" --out "$RUN" --extra "$FIX/explain.json" ${UNDERSTANDO_VE_RUNTIME:+--runtime "$UNDERSTANDO_VE_RUNTIME"} >/dev/null
node "$ROOT/learn/web/scripts/compile-chapters.mjs" "$RUN"
echo "fixture run: $RUN (head $HEAD)"
