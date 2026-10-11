#!/usr/bin/env bash
# Model-free smoke run of understando learn on the fixture run (built by make-fixture-run.sh in a
# temp folder, so no real run or ~/.understando state is read): start, load the chapters, run one
# control, stop. It makes no tutor call. The level count comes from the compiled chapters.json.
set -euo pipefail
L="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
W="$(mktemp -d "${TMPDIR:-/tmp}/learn-smoke.XXXXXX")"
bash "$L/web/e2e/make-fixture-run.sh" "$W" >/dev/null
RUN="$W/run"
REPO="$W/repo"
CONTROL="${SMOKE_CONTROL:-K01}"
PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')"
O="http://127.0.0.1:$PORT"
LOG="$W/learn.log"
BEFORE="$(git -C "$REPO" worktree list --porcelain)"
# The tutor CLIs are not on PATH for this run, so no model call can start.
PATH="$(dirname "$(command -v git)"):$(dirname "$(command -v python3)"):$(dirname "$(command -v uv)"):$(dirname "$(command -v node)"):/usr/bin:/bin" \
  "$L/learn.sh" "$RUN" --repo "$REPO" --port "$PORT" --no-open >"$LOG" 2>&1 &
PID=$!
trap 'kill -TERM $PID 2>/dev/null || true; rm -rf "$W"' EXIT
for _ in $(seq 1 200); do curl -sf "$O/api/health" >/dev/null && break; sleep 0.2; done
SCRATCH="$(sed -n 's/^scratch: //p' "$LOG")"
echo "started: $O, scratch $SCRATCH"
python3 - "$O" "$CONTROL" "$RUN/learn/chapters.json" <<'PY'
import json, sys, time, urllib.request, urllib.error
origin, control, compiled = sys.argv[1:4]
ch = json.load(urllib.request.urlopen(origin + "/api/chapters"))
print("chapters:", [c["title"] for c in ch["chapters"]])
want = [c["title"] for c in json.load(open(compiled))["chapters"]]
assert want, "the compiled chapters.json holds no level"
assert [c["title"] for c in ch["chapters"]] == want, "the app serves the levels of the explainer data, in order"
req = lambda: urllib.request.Request(origin + "/api/run", data=json.dumps({"kind": "run-control", "id": control}).encode(),
                                     headers={"Content-Type": "application/json", "Origin": origin}, method="POST")
start = time.time()
while True:  # The worktree setup (uv sync) runs first and holds the slot.
    try:
        body = urllib.request.urlopen(req(), timeout=1800).read().decode()
        break
    except urllib.error.HTTPError as e:
        if e.code != 409 or time.time() - start > 900: raise
        time.sleep(2)
events = [json.loads(l) for l in body.splitlines() if l.strip()]
result = next(e["result"] for e in events if e["type"] == "result")
print(f"control {control}: {result['status']} (exit {result.get('exit')}, {result.get('seconds')} s, matched {result.get('matched')}), recorded {result['recorded']['status']}")
print(f"wall time with reset and setup: {round(time.time() - start, 1)} s")
assert result["status"] == result["recorded"]["status"] == "red" and result["matched"] is True, result
PY
kill -TERM "$PID"; wait "$PID" || true; trap - EXIT
tail -1 "$LOG"
[ -n "$SCRATCH" ] && test ! -e "$SCRATCH" || { echo "FAIL: the scratch folder is left: $SCRATCH"; exit 1; }
test "$(git -C "$REPO" worktree list --porcelain)" = "$BEFORE" || { echo "FAIL: the worktree list of $REPO changed"; exit 1; }
rm -rf "$W"
echo "PASS: fixture smoke run (start, load, one control, stop)"
