#!/usr/bin/env bash
# understando global setup. Idempotent. It ends with doctor.
#
#   scripts/setup.sh           install what is missing, then run doctor
#   scripts/setup.sh doctor    only report what is present and what is missing
#
# Global writes, each one listed by doctor:
#   1. symlinks named understando in ~/.agents/skills, ~/.claude/skills, ~/.codex/skills and
#      ~/.cursor/skills. The script makes a link only when the name is free, or when the name is
#      already a link to this repo. It never replaces another skill.
#   2. the Code Contracts skill: npx skills add https://github.com/spolu/code-contracts
#   3. cc-check through npx (@spolu/cc-check, pinned below) in the npm cache. No global npm install.
#   4. only when missing: the pstack verification skills, asd-ste100 and visual-explainer.
# Telemetry: DO_NOT_TRACK=1, DISABLE_TELEMETRY=1 and E2E_TELEMETRY_DISABLED=1 for every npx call.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CC_CHECK_SPEC="@spolu/cc-check@0.2.0"
SKILL_DIRS=("$HOME/.agents/skills" "$HOME/.claude/skills" "$HOME/.codex/skills" "$HOME/.cursor/skills")
export DO_NOT_TRACK=1 DISABLE_TELEMETRY=1 E2E_TELEMETRY_DISABLED=1

missing=0
say() { printf '%-9s %-34s %s\n' "$1" "$2" "$3"; }
ok() { say "ok" "$1" "$2"; }
bad() { say "MISSING" "$1" "$2"; missing=$((missing + 1)); }
warn() { say "warn" "$1" "$2"; }

find_skill() { # name -> first SKILL.md path that exists
  local name="$1" d
  for d in "$HOME/.agents/skills/$name" "$HOME/.claude/skills/$name" \
           "$HOME/.claude/skills/pstack/skills/$name" "$HOME/.codex/skills/$name" "$HOME/.cursor/skills/$name"; do
    if [ -f "$d/SKILL.md" ]; then echo "$d"; return 0; fi
  done
  return 1
}

link_skill() {
  local dir="$1" target="$1/understando"
  mkdir -p "$dir"
  if [ -L "$target" ]; then
    if [ "$(readlink "$target")" = "$ROOT" ]; then return 0; fi
    echo "refuse: $target is a link to $(readlink "$target"), not to $ROOT" >&2; return 1
  fi
  if [ -e "$target" ]; then echo "refuse: $target exists and is not an understando link" >&2; return 1; fi
  ln -s "$ROOT" "$target" && echo "linked $target -> $ROOT"
}

skills_add() { # url [skills-cli flags...]
  npx --yes skills add "$@" -g -y -a claude-code -a codex -a cursor
}

install() {
  local d
  for d in "${SKILL_DIRS[@]}"; do link_skill "$d"; done
  if ! find_skill code-contracts >/dev/null; then
    skills_add https://github.com/spolu/code-contracts -s code-contracts
  fi
  npx --yes "$CC_CHECK_SPEC" --help >/dev/null 2>&1 || echo "cc-check did not start through npx" >&2
  if ! find_skill create-verification-skill >/dev/null || ! find_skill maintain-verification-skill >/dev/null; then
    skills_add https://github.com/cursor/plugins --full-depth -s create-verification-skill -s maintain-verification-skill
  fi
  find_skill asd-ste100 >/dev/null || skills_add https://github.com/danyuchn/asd-ste100-skill
  find_skill visual-explainer >/dev/null || skills_add https://github.com/theclaymethod/artifacture -s visual-explainer
}

doctor() {
  local d p v
  echo "understando doctor ($ROOT)"
  for d in "${SKILL_DIRS[@]}"; do
    if [ -L "$d/understando" ] && [ "$(readlink "$d/understando")" = "$ROOT" ]; then ok "link $d/understando" "-> $ROOT"
    elif [ -e "$d/understando" ]; then bad "link $d/understando" "another skill holds the name"
    else bad "link $d/understando" "absent"; fi
  done
  for p in git python3 node npx; do
    if command -v "$p" >/dev/null; then ok "$p" "$(command -v "$p")"; else bad "$p" "not on PATH"; fi
  done
  v="$(node -p 'process.versions.node' 2>/dev/null || echo 0)"
  if node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>22||(a===22&&b>=12)?0:1)' 2>/dev/null
  then ok "node >= 22.12" "$v"; else bad "node >= 22.12" "$v"; fi
  if python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then ok "python3 >= 3.9" "$(python3 -V 2>&1)"
  else bad "python3 >= 3.9" "$(python3 -V 2>&1)"; fi
  for p in code-contracts create-verification-skill maintain-verification-skill asd-ste100 visual-explainer; do
    if d="$(find_skill "$p")"; then ok "skill $p" "$d"; else bad "skill $p" "not installed"; fi
  done
  if d="$(find_skill asd-ste100)" && [ -f "$d/scripts/ste-lint.py" ]; then ok "ste-lint.py" "$d/scripts/ste-lint.py"
  else bad "ste-lint.py" "not found"; fi
  if npx --no-install "$CC_CHECK_SPEC" --help >/dev/null 2>&1; then ok "cc-check" "npx $CC_CHECK_SPEC (npm cache)"
  else bad "cc-check" "run scripts/setup.sh"; fi
  if d="$(find_skill visual-explainer)" && p="$(node "$d/scripts/artifacture.mjs" path 2>/dev/null | tail -1)" && [ -d "$p/visual-explainer-mdx" ]
  then ok "visual-explainer runtime" "$p"; else bad "visual-explainer runtime" "artifacture.mjs path failed"; fi
  if command -v gh >/dev/null; then ok "gh (optional)" "$(command -v gh)"; else warn "gh (optional)" "needed to read a PR"; fi
  if command -v uv >/dev/null; then ok "uv (optional)" "$(command -v uv)"; else warn "uv (optional)" "needed by Python targets"; fi
  warn "tester-army e2e" "per repo only, after approval: E2E_TELEMETRY_DISABLED=1 npx e2e init"
  if [ "$missing" -eq 0 ]; then echo "doctor: every required piece is present"; return 0; fi
  echo "doctor: $missing required pieces are missing"; return 1
}

case "${1:-install}" in
  doctor) doctor ;;
  install) install; doctor ;;
  *) echo "usage: scripts/setup.sh [doctor]" >&2; exit 2 ;;
esac
