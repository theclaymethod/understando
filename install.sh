#!/bin/bash
set -eu

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
destination=".claude/skills/understando"
mkdir -p "$destination"
if ! [[ "$source_dir/SKILL.md" -ef "$destination/SKILL.md" ]]; then
  cp "$source_dir/SKILL.md" "$destination/SKILL.md"
fi

for settings in .claude/settings.json .claude/settings.local.json; do
  [[ -f "$settings" ]] && grep -qF 'understando-gate.sh' "$settings" || continue
  python3 - "$settings" <<'PY'
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

path = Path(sys.argv[1]).resolve()
config = json.loads(path.read_text())
groups = config.get("hooks", {}).get("PreToolUse", [])
legacy = '"$CLAUDE_PROJECT_DIR"/.claude/hooks/understando-gate.sh'
retained = []
changed = False
for group in groups:
    hooks = group.get("hooks", [])
    keep = [h for h in hooks if not (
        group.get("matcher") == "Bash" and h.get("type") == "command"
        and h.get("command") == legacy
    )]
    if len(keep) == len(hooks):
        retained.append(group)
    else:
        changed = True
        if keep:
            retained.append(dict(group, hooks=keep))

if changed:
    config["hooks"]["PreToolUse"] = retained
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as tmp:
        json.dump(config, tmp, indent=2, ensure_ascii=False)
        tmp.write("\n")
    try:
        os.chmod(tmp.name, stat.S_IMODE(path.stat().st_mode))
        os.replace(tmp.name, path)
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    print(f"Removed the original Understando commit hook from {path}")
PY
done

echo "Installed Understando in $destination"
