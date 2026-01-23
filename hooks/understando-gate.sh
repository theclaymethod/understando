#!/bin/bash
# Understando Pre-Commit Gate
# Intercepts git commit commands and triggers the understando quiz
# unless the --understando-passed flag is present

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

# Check for --understando-passed flag (quiz already passed)
if [[ "$command" == *"--understando-passed"* ]]; then
  # Strip the flag and allow the commit
  # Output modified command for Claude to use
  modified_command=$(echo "$command" | sed 's/--understando-passed//g' | sed 's/  */ /g' | sed 's/ *$//')
  echo "{\"modifiedCommand\": \"$modified_command\"}" >&2
  exit 0
fi

# Block the commit and instruct Claude to run the quiz
cat >&2 << 'EOF'
UNDERSTANDO QUIZ REQUIRED

Before committing, you must pass the Understando quiz to verify you understand the code changes.

Please run the /understando skill now to start the quiz.

After passing (or choosing to skip), retry the commit with the --understando-passed flag.
EOF

exit 2
