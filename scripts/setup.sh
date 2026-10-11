#!/usr/bin/env bash
# understando global setup. Idempotent. It ends with doctor.
#
#   scripts/setup.sh [--scope project|global]   install what is missing, then run doctor
#   scripts/setup.sh --links-only               only the skill links and the CLI link
#   scripts/setup.sh --ve-runtime PATH          pin the visual-explainer runtime in ~/.understando/config.toml
#   scripts/setup.sh doctor                     only report what is present and what is missing
#
# The optional external skills (Code Contracts, the pstack verification skills, asd-ste100,
# visual-explainer) go to the project (./.agents/skills) or to the user's global skill folders.
# The script asks which, unless --scope or $UNDERSTANDO_SETUP_SCOPE says it. Without a terminal and
# without a scope, it installs no optional skill.
#
# The prompt hook (hooks/user-prompt-submit.json) is optional. The script prints it and asks before
# it adds it to ~/.claude/settings.json or ~/.codex/hooks.json. It writes a backup first. Without a
# terminal it only prints the snippet.
#
# Global writes, each one listed by doctor:
#   0. the CLI: a link ~/.local/bin/understando -> bin/understando, made only when the name is free.
#      When ~/.local/bin is not on PATH, setup prints the one line to add to the shell rc.
#   0b. ve_runtime in ~/.understando/config.toml: the visual-explainer runtime. setup asks once.
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

SCOPE="${UNDERSTANDO_SETUP_SCOPE:-}"
skills_add() { # url [skills-cli flags...]
  case "$SCOPE" in
    global) npx --yes skills add "$@" -g -y -a claude-code -a codex -a cursor ;;
    project) npx --yes skills add "$@" -y -a claude-code -a codex -a cursor ;;
    *) echo "skip: $* (no scope chosen)" ;;
  esac
}

ask_scope() {
  [ -n "$SCOPE" ] && return 0
  if [ -t 0 ]; then
    printf 'Install the optional skills for this project or globally? [project/global/skip] '
    read -r SCOPE
  fi
  case "$SCOPE" in project|global) ;; *) SCOPE=skip ;; esac
}

link_cli() {
  local bin="$HOME/.local/bin" target="$HOME/.local/bin/understando"
  mkdir -p "$bin"
  if [ -L "$target" ] && [ "$(readlink "$target")" = "$ROOT/bin/understando" ]; then return 0; fi
  if [ -e "$target" ] || [ -L "$target" ]; then echo "refuse: $target exists and is not the understando CLI" >&2; return 1; fi
  ln -s "$ROOT/bin/understando" "$target" && echo "linked $target -> $ROOT/bin/understando"
}

path_hint() { python3 "$ROOT/scripts/setup.py" path-hint; }

offer_hook() { # settings file
  local file="$1"
  echo "Optional prompt hook for $file. It notes each prompt only while the mode is on:"
  cat "$ROOT/hooks/user-prompt-submit.json"
  if [ ! -t 0 ]; then echo "not installed: no terminal to ask. Add the snippet by hand, or run setup in a terminal."; return 0; fi
  printf 'Add it to %s? [y/N] ' "$file"
  read -r yes
  [ "$yes" = "y" ] || [ "$yes" = "Y" ] || { echo "not installed"; return 0; }
  python3 - "$file" "$ROOT/hooks/user-prompt-submit.json" <<'PY'
import json, shutil, sys
from pathlib import Path
target, snippet = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())
data = json.loads(target.read_text()) if target.is_file() and target.read_text().strip() else {}
if target.is_file():
    shutil.copyfile(target, str(target) + ".understando-backup")
hooks = data.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
entry = snippet["hooks"]["UserPromptSubmit"][0]
if entry not in hooks:
    hooks.append(entry)
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(data, indent=2) + "\n")
print(f"installed the prompt hook in {target} (backup: {target}.understando-backup)")
PY
}

links() {
  local d
  for d in "${SKILL_DIRS[@]}"; do link_skill "$d"; done
  link_cli
  path_hint
}

install() {
  links
  python3 "$ROOT/scripts/setup.py" ve-runtime ${VE_RUNTIME:+--set "$VE_RUNTIME"}
  ask_scope
  if ! find_skill code-contracts >/dev/null; then
    skills_add https://github.com/spolu/code-contracts -s code-contracts
  fi
  npx --yes "$CC_CHECK_SPEC" --help >/dev/null 2>&1 || echo "cc-check did not start through npx" >&2
  if ! find_skill create-verification-skill >/dev/null || ! find_skill maintain-verification-skill >/dev/null; then
    skills_add https://github.com/cursor/plugins --full-depth -s create-verification-skill -s maintain-verification-skill
  fi
  find_skill asd-ste100 >/dev/null || skills_add https://github.com/danyuchn/asd-ste100-skill
  find_skill visual-explainer >/dev/null || skills_add https://github.com/theclaymethod/artifacture -s visual-explainer
  offer_hook "$HOME/.claude/settings.json"
  if command -v codex >/dev/null && codex features list 2>/dev/null | grep -Eq '^hooks[[:space:]]+[a-z]+[[:space:]]+true'; then
    offer_hook "$HOME/.codex/hooks.json"
  fi
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
  if p="$(python3 "$ROOT/scripts/config.py" ve-runtime)" && [ -f "$p/visual-explainer-mdx/components.tsx" ] && [ -f "$p/scripts/artifacture.mjs" ] && [ -d "$p/node_modules/playwright" ]
  then ok "visual-explainer runtime" "$p"; else bad "visual-explainer runtime" "ve_runtime unset or incomplete: setup --ve-runtime PATH"; fi
  if [ -L "$HOME/.local/bin/understando" ] && [ "$(readlink "$HOME/.local/bin/understando")" = "$ROOT/bin/understando" ]; then ok "cli ~/.local/bin/understando" "-> $ROOT/bin/understando"
  else bad "cli ~/.local/bin/understando" "absent"; fi
  case ":$PATH:" in *":$HOME/.local/bin:"*) ok "PATH" "holds ~/.local/bin" ;; *) bad "PATH" "lacks ~/.local/bin"; path_hint ;; esac
  if p="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import ctx; print(ctx.java_bin() or "")' "$ROOT/scripts")" && [ -n "$p" ]
  then ok "java (formalize only)" "$p"; else warn "java (formalize only)" "no JAVA_HOME, no Homebrew openjdk, no java on PATH"; fi
  if [ -f "$HOME/.understando/tools/tla2tools.jar" ]; then ok "tla2tools.jar (formalize only)" "$HOME/.understando/tools/tla2tools.jar"
  else warn "tla2tools.jar (formalize only)" "put it at ~/.understando/tools/tla2tools.jar"; fi
  if command -v gh >/dev/null; then ok "gh (optional)" "$(command -v gh)"; else warn "gh (optional)" "needed to read a PR"; fi
  if command -v uv >/dev/null; then ok "uv (optional)" "$(command -v uv)"; else warn "uv (optional)" "needed by Python targets"; fi
  warn "tester-army e2e" "per repo only, after approval: E2E_TELEMETRY_DISABLED=1 npx e2e init"
  if [ "$missing" -eq 0 ]; then echo "doctor: every required piece is present"; return 0; fi
  echo "doctor: $missing required pieces are missing"; return 1
}

ACTION=install
VE_RUNTIME=""
while [ $# -gt 0 ]; do
  case "$1" in
    doctor) ACTION=doctor ;;
    --links-only) ACTION=links ;;
    --scope) SCOPE="$2"; shift ;;
    --ve-runtime) VE_RUNTIME="$2"; ACTION=ve; shift ;;
    *) echo "usage: scripts/setup.sh [doctor | --links-only | --scope project|global | --ve-runtime PATH]" >&2; exit 2 ;;
  esac
  shift
done
case "$ACTION" in
  doctor) doctor ;;
  links) links ;;
  ve) python3 "$ROOT/scripts/setup.py" ve-runtime --set "$VE_RUNTIME" ;;
  install) install; doctor ;;
esac
