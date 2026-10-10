#!/usr/bin/env bash
# Model-free smoke run of understando learn on runs/function-intelligence/489:
# start, load the chapters, run one control, stop. It makes no tutor call.
set -euo pipefail
L="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN="$(cd "$L/../runs/function-intelligence/489" && pwd)"
REPO="${FI_REPO:-$HOME/dev/function-intelligence}"
CONTROL="${SMOKE_CONTROL:-K08}"
[ -d "$REPO/.git" ] || { echo "SKIP: no clone at $REPO"; exit 0; }
PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')"
O="http://127.0.0.1:$PORT"
LOG="$(mktemp -t learn-489)"
BEFORE="$(git -C "$REPO" worktree list --porcelain)"
# The tutor CLIs are not on PATH for this run, so no model call can start.
PATH="$(dirname "$(command -v git)"):$(dirname "$(command -v python3)"):$(dirname "$(command -v uv)"):$(dirname "$(command -v node)"):/usr/bin:/bin" \
  "$L/learn.sh" "$RUN" --repo "$REPO" --port "$PORT" --no-open >"$LOG" 2>&1 &
PID=$!
trap 'kill -TERM $PID 2>/dev/null || true' EXIT
for _ in $(seq 1 200); do curl -sf "$O/api/health" >/dev/null && break; sleep 0.2; done
SCRATCH="$(sed -n 's/^scratch: //p' "$LOG")"
echo "started: $O, scratch $SCRATCH"
python3 - "$O" "$CONTROL" <<'PY'
import json, sys, time, urllib.request, urllib.error
origin, control = sys.argv[1], sys.argv[2]
ch = json.load(urllib.request.urlopen(origin + "/api/chapters"))
print("chapters:", [c["title"] for c in ch["chapters"]])
assert len(ch["chapters"]) == 6, "expected six chapters"
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
test ! -e "$SCRATCH" || { echo "FAIL: the scratch folder is left: $SCRATCH"; exit 1; }
test "$(git -C "$REPO" worktree list --porcelain)" = "$BEFORE" || { echo "FAIL: the worktree list of $REPO changed"; exit 1; }
echo "PASS: #489 smoke run (start, load, one control, stop)"
