#!/usr/bin/env bash
# understando global setup. Idempotent. It ends with `understando doctor`.
#
#   scripts/setup.sh [--scope project|global]   install what is missing, then run doctor
#   scripts/setup.sh --links-only               only the skill links and the CLI link
#   scripts/setup.sh --mutation                 only the mutation venv (mutmut, cosmic-ray, pytest)
#
# Global writes:
#   1. the CLI: a link ~/.local/bin/understando -> bin/understando, made only when the name is free;
#   2. symlinks named understando in ~/.agents/skills, ~/.claude/skills, ~/.codex/skills and
#      ~/.cursor/skills, made only when the name is free or is already a link to this repo;
#   3. the mutation venv ~/.understando/tools/mutation (uv venv, then mutmut, cosmic-ray, pytest from PyPI);
#   4. only when missing, and only for the chosen scope: the Code Contracts skill, the pstack
#      verification skills, asd-ste100 and visual-explainer; cc-check through npx (the npm cache).
# Telemetry: DO_NOT_TRACK=1, DISABLE_TELEMETRY=1 for every npx call.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CC_CHECK_SPEC="@spolu/cc-check@0.2.0"
SKILL_DIRS=("$HOME/.agents/skills" "$HOME/.claude/skills" "$HOME/.codex/skills" "$HOME/.cursor/skills")
MUTATION_VENV="${UNDERSTANDO_HOME:-$HOME/.understando}/tools/mutation"
export DO_NOT_TRACK=1 DISABLE_TELEMETRY=1

find_skill() {
  local d
  for d in "$HOME/.agents/skills/$1" "$HOME/.claude/skills/$1" "$HOME/.claude/skills/pstack/skills/$1" \
           "$HOME/.codex/skills/$1" "$HOME/.cursor/skills/$1"; do
    if [ -f "$d/SKILL.md" ]; then echo "$d"; return 0; fi
  done
  return 1
}

link_skill() {
  local target="$1/understando"
  mkdir -p "$1"
  if [ -L "$target" ]; then
    [ "$(readlink "$target")" = "$ROOT" ] && return 0
    echo "refuse: $target is a link to $(readlink "$target"), not to $ROOT" >&2; return 1
  fi
  if [ -e "$target" ]; then echo "refuse: $target exists and is not an understando link" >&2; return 1; fi
  ln -s "$ROOT" "$target" && echo "linked $target -> $ROOT"
}

link_cli() {
  local target="$HOME/.local/bin/understando"
  mkdir -p "$HOME/.local/bin"
  if [ -L "$target" ] && [ "$(readlink "$target")" = "$ROOT/bin/understando" ]; then return 0; fi
  if [ -e "$target" ] || [ -L "$target" ]; then echo "refuse: $target exists and is not the understando CLI" >&2; return 1; fi
  ln -s "$ROOT/bin/understando" "$target" && echo "linked $target -> $ROOT/bin/understando"
  case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "add this line to your shell rc: export PATH=\"\$HOME/.local/bin:\$PATH\"" ;; esac
}

links() {
  local d
  for d in "${SKILL_DIRS[@]}"; do link_skill "$d"; done
  link_cli
}

mutation() {
  if [ -x "$MUTATION_VENV/bin/mutmut" ] && [ -x "$MUTATION_VENV/bin/cosmic-ray" ]; then echo "ok: the mutation venv $MUTATION_VENV"; return 0; fi
  command -v uv >/dev/null || { echo "refuse: uv is not on PATH; install uv, or make a venv with mutmut, cosmic-ray and pytest and pass --venv" >&2; return 1; }
  uv venv -q "$MUTATION_VENV" && VIRTUAL_ENV="$MUTATION_VENV" uv pip install -q mutmut cosmic-ray pytest && echo "made the mutation venv $MUTATION_VENV"
}

SCOPE="${UNDERSTANDO_SETUP_SCOPE:-}"
skills_add() {
  case "$SCOPE" in
    global) npx --yes skills add "$@" -g -y -a claude-code -a codex -a cursor ;;
    project) npx --yes skills add "$@" -y -a claude-code -a codex -a cursor ;;
    *) echo "skip: $* (no scope chosen)" ;;
  esac
}

install() {
  links
  mutation
  if [ -z "$SCOPE" ] && [ -t 0 ]; then printf 'Install the optional skills for this project or globally? [project/global/skip] '; read -r SCOPE; fi
  find_skill code-contracts >/dev/null || skills_add https://github.com/spolu/code-contracts -s code-contracts
  npx --yes "$CC_CHECK_SPEC" --help >/dev/null 2>&1 || echo "cc-check did not start through npx" >&2
  if ! find_skill create-verification-skill >/dev/null || ! find_skill maintain-verification-skill >/dev/null; then
    skills_add https://github.com/cursor/plugins --full-depth -s create-verification-skill -s maintain-verification-skill
  fi
  find_skill asd-ste100 >/dev/null || skills_add https://github.com/danyuchn/asd-ste100-skill
  find_skill visual-explainer >/dev/null || skills_add https://github.com/theclaymethod/artifacture -s visual-explainer
}

ACTION=install
while [ $# -gt 0 ]; do
  case "$1" in
    --links-only) ACTION=links ;;
    --mutation) ACTION=mutation ;;
    --scope) SCOPE="$2"; shift ;;
    *) echo "usage: scripts/setup.sh [--links-only | --mutation | --scope project|global]" >&2; exit 2 ;;
  esac
  shift
done
case "$ACTION" in
  links) links ;;
  mutation) mutation ;;
  install) install; "$ROOT/bin/understando" doctor ;;
esac
