#!/usr/bin/env bash
# Install Lean, Java, tla2tools.jar and mutmut, and link the skill. Idempotent: each line says ok, made or missing.
#
#   scripts/setup.sh               link the skill, then install the tools
#   scripts/setup.sh --links-only  only link the skill
#   scripts/setup.sh --check       report only; change nothing
#
# Writes: a link named understando in ~/.agents/skills, ~/.claude/skills, ~/.codex/skills and
# ~/.cursor/skills (only when the name is free or already links here); under ~/.understando/tools:
# elan (only when no elan is on PATH), tla2tools.jar, and the venv mutation/ (mutmut, pytest);
# Homebrew openjdk when no Java runs. It never touches ~/.understando/runs. Exit 1 when a part is missing.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS="$HOME/.understando/tools"
TLA_URL="https://github.com/tlaplus/tlaplus/releases/download/v1.8.0/tla2tools.jar"
ELAN_URL="https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh"
MODE=install
MISSING=0

case "${1:-}" in
  "") ;;
  --links-only) MODE=links ;;
  --check) MODE=check ;;
  -h|--help) sed -n '2,/^[^#]/{/^#/!d;s/^# \{0,1\}//;p;}' "$0"; exit 0 ;;
  *) echo "usage: scripts/setup.sh [--links-only | --check]" >&2; exit 2 ;;
esac

ok() { echo "ok:      $*"; }
made() { echo "made:    $*"; }
missing() { echo "missing: $*"; MISSING=1; }
doing() { [ "$MODE" != check ]; }

link_skill() {
  local target="$1/understando"
  if [ -L "$target" ] && [ "$(readlink "$target")" = "$ROOT" ]; then ok "$target -> $ROOT"; return; fi
  if [ -e "$target" ] || [ -L "$target" ]; then missing "$target exists and does not link to $ROOT; move it, then run again"; return; fi
  if doing; then mkdir -p "$1" && ln -s "$ROOT" "$target" && made "$target -> $ROOT"; else missing "$target"; fi
}

elan_bin() {
  if command -v elan >/dev/null 2>&1; then command -v elan; return; fi
  [ -x "$TOOLS/elan/bin/elan" ] && echo "$TOOLS/elan/bin/elan"
}

step_lean() {
  local elan; elan="$(elan_bin)"
  if [ -z "$elan" ]; then
    if doing; then
      curl -sSfL "$ELAN_URL" | ELAN_HOME="$TOOLS/elan" sh -s -- -y --no-modify-path --default-toolchain stable >/dev/null \
        && made "elan and Lean stable in $TOOLS/elan (add $TOOLS/elan/bin to PATH)" || missing "elan: the installer failed"
    else missing "elan (Lean)"; fi
    return
  fi
  if "$elan" toolchain list 2>/dev/null | grep -q 'leanprover'; then ok "Lean: $("$elan" toolchain list | head -1)"; return; fi
  if doing; then "$elan" toolchain install stable >/dev/null 2>&1 && "$elan" default stable >/dev/null 2>&1 \
    && made "Lean stable toolchain" || missing "Lean: elan toolchain install stable failed"
  else missing "a Lean toolchain (elan toolchain install stable)"; fi
}

java_bin() {
  local j
  for j in "${JAVA_HOME:-/nonexistent}/bin/java" "$(brew --prefix openjdk 2>/dev/null)/bin/java" "$(command -v java 2>/dev/null)"; do
    [ -x "$j" ] && "$j" -version >/dev/null 2>&1 && { echo "$j"; return; }
  done
}

step_java() {
  local j; j="$(java_bin)"
  if [ -n "$j" ]; then ok "Java: $j"; return; fi
  if doing && command -v brew >/dev/null 2>&1; then
    brew install openjdk >/dev/null && made "Java: $(brew --prefix openjdk)/bin/java" || missing "Java: brew install openjdk failed"
  else missing "Java (brew install openjdk)"; fi
}

step_tla() {
  if [ -s "$TOOLS/tla2tools.jar" ]; then ok "TLC: $TOOLS/tla2tools.jar"; return; fi
  if doing; then mkdir -p "$TOOLS" && curl -sSfL -o "$TOOLS/tla2tools.jar.part" "$TLA_URL" \
    && mv "$TOOLS/tla2tools.jar.part" "$TOOLS/tla2tools.jar" && made "TLC: $TOOLS/tla2tools.jar" || missing "TLC: the download failed"
  else missing "TLC ($TOOLS/tla2tools.jar)"; fi
}

step_mutation() {
  local v="$TOOLS/mutation"
  if [ -x "$v/bin/mutmut" ] && [ -x "$v/bin/pytest" ]; then ok "mutmut: $v/bin/mutmut"; return; fi
  if ! doing; then missing "mutmut and pytest ($v)"; return; fi
  if command -v uv >/dev/null 2>&1; then
    uv venv -q "$v" && VIRTUAL_ENV="$v" uv pip install -q mutmut pytest
  else
    python3 -m venv "$v" && "$v/bin/pip" install -q mutmut pytest
  fi && made "mutmut: $v/bin/mutmut" || missing "mutmut: the install failed"
}

for d in "$HOME/.agents/skills" "$HOME/.claude/skills" "$HOME/.codex/skills" "$HOME/.cursor/skills"; do link_skill "$d"; done
if [ "$MODE" != links ]; then step_lean; step_java; step_tla; step_mutation; fi
exit "$MISSING"
