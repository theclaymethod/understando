#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
FAILED=0
pass() { echo "PASS $*"; }
fail() { echo "FAIL $*"; FAILED=1; }

# 1. Check discovery fields and the entry point a project actually installs.
if awk '
  NR == 1 { if ($0 != "---") exit 1; next }
  /^---$/ { closed = 1; exit }
  /^name: understando$/ { named = 1 }
  /^description: [^[:space:]]/ { described = 1 }
  END { exit !(named && described && closed) }
' "$ROOT/SKILL.md"; then
  pass "skill discovery metadata"
else
  fail "missing skill discovery metadata"
fi

# Compare the independently installable skills when a CStack checkout is available.
if [ -n "${BOOTSTRAP_SKILL:-}" ]; then
  if python3 - "$BOOTSTRAP_SKILL" "$ROOT/SKILL.md" <<'PYTHON'
from pathlib import Path
import sys

def interview(path):
    text = Path(path).read_text()
    heading = "## Intent interview\n"
    if text.count(heading) != 1:
        raise SystemExit(f"Expected one intent interview section in {path}")
    return text.split(heading, 1)[1].split("\n## ", 1)[0].strip()

bootstrap, understando = map(interview, sys.argv[1:])
sys.exit(0 if bootstrap and bootstrap == understando else 1)
PYTHON
  then pass "interview matches Bootstrap"
  else fail "interview differs from Bootstrap"
  fi
fi

mkdir -p "$T/project"
if (cd "$T/project" && "$ROOT/install.sh" && "$ROOT/install.sh") > "$T/install" 2>&1 &&
   cmp -s "$ROOT/SKILL.md" "$T/project/.claude/skills/understando/SKILL.md" &&
   [ ! -e "$T/project/.claude/settings.json" ]; then
  pass "project install, repeat install, and no commit hook"
else
  fail "project install: $(cat "$T/install")"
fi

# Upgrade a project with both the original hook and an unrelated Bash hook.
python3 - "$T/project" <<'PY' || exit 1
import json
from pathlib import Path
import sys

directory = Path(sys.argv[1]) / ".claude"
for name in ("settings.json", "settings.local.json"):
    original = {"type": "command", "command": '"$CLAUDE_PROJECT_DIR"/.claude/hooks/understando-gate.sh'}
    other = {"type": "command", "command": "echo understando-gate.sh"}
    config = {"permissions": {"allow": []}, "hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [original]},
        {"matcher": "Bash", "hooks": [other, original]},
    ]}}
    (directory / name).write_text(json.dumps(config))
PY
(cd "$T/project" && "$ROOT/install.sh" && "$ROOT/install.sh") || exit 1
python3 - "$T/project" <<'PY' || exit 1
import json
from pathlib import Path
import sys

for name in ("settings.json", "settings.local.json"):
    actual = json.loads((Path(sys.argv[1]) / ".claude" / name).read_text())
    assert actual == {"permissions": {"allow": []}, "hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo understando-gate.sh"}]}
    ]}}, actual
PY
pass "upgrade removes the quiz gate and preserves neighboring settings"
exit "$FAILED"
