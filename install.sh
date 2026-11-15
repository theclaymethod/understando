#!/bin/bash
set -eu

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
destination=".claude/skills/understando"
mkdir -p "$destination"
cp "$source_dir/SKILL.md" "$destination/SKILL.md"
echo "Installed Understando in $destination"
if [[ -f .claude/settings.json ]] && grep -q 'understando-gate.sh' .claude/settings.json; then
  echo "The old quiz hook is still registered. See the upgrade instructions in README.md."
fi
