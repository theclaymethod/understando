#!/bin/bash
# Understando Installer
# Run this script from your project root to install Understando

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing Understando..."

# Create directories
mkdir -p .claude/skills/understando
mkdir -p .claude/hooks

# Copy skill
cp "$SCRIPT_DIR/SKILL.md" .claude/skills/understando/
echo "  Copied skill to .claude/skills/understando/"

# Copy hook
cp "$SCRIPT_DIR/hooks/understando-gate.sh" .claude/hooks/
chmod +x .claude/hooks/understando-gate.sh
echo "  Copied hook to .claude/hooks/"

# Copy example config
if [[ ! -f .understando.json ]]; then
  cp "$SCRIPT_DIR/understando.json" .understando.json
  echo "  Created .understando.json config"
else
  echo "  .understando.json already exists, skipping"
fi

# Handle settings.json
if [[ -f .claude/settings.json ]]; then
  echo ""
  echo "  Found existing .claude/settings.json"
  echo "  Please manually merge the hook configuration from:"
  echo "  $SCRIPT_DIR/settings/hooks.json"
  echo ""
else
  cp "$SCRIPT_DIR/settings/hooks.json" .claude/settings.json
  echo "  Created .claude/settings.json"
fi

echo ""
echo "Installation complete!"
echo ""
echo "To verify, try committing through Claude Code:"
echo "  > commit these changes"
echo ""
echo "You should see the Understando quiz prompt."
