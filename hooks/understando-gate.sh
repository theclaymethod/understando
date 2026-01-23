#!/bin/bash
# Understando Pre-Commit Gate
# Intercepts git commit commands and triggers the understando quiz
# unless the quiz was already passed (indicated by .understando-passed file)

set -e

# Read JSON input from stdin
input=$(cat)

# Extract tool name and command
tool_name=$(echo "$input" | jq -r '.tool_name // ""')
command=$(echo "$input" | jq -r '.tool_input.command // ""')

# Only intercept Bash tool calls
if [[ "$tool_name" != "Bash" ]]; then
  exit 0
fi

# Only intercept git commit commands
if [[ "$command" != *"git commit"* ]]; then
  exit 0
fi

# Check for quiz-passed marker file in project directory
MARKER_FILE="${CLAUDE_PROJECT_DIR:-.}/.understando-passed"
if [[ -f "$MARKER_FILE" ]]; then
  # Quiz was passed, allow commit and clean up marker
  rm -f "$MARKER_FILE"
  exit 0
fi

# Block the commit and instruct Claude to run the quiz
cat >&2 << 'EOF'
UNDERSTANDO QUIZ REQUIRED

Before committing, you must pass the Understando quiz to verify you understand the code changes.

Please run the /understando skill now to start the quiz.

After passing (or choosing to skip), the commit will proceed automatically.
EOF

exit 2
