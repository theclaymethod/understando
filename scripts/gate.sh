#!/usr/bin/env bash
# The verifier-first gate: edits to source files are denied until a verifier has been seen to fail.
#
#   scripts/gate.sh start INVARIANT                begin a behavior. INVARIANT is the user's words. Closes the gate.
#   scripts/gate.sh red -- COMMAND...              run the verifier on the current tree. It must fail. Opens the gate.
#   scripts/gate.sh red --control CONTROL_ARGS... -- COMMAND...
#                                                  for a behavior that exists already: control.sh plants a bug
#                                                  (see control.sh --help) and the verifier must fail on it.
#   scripts/gate.sh green -- COMMAND...            run the verifier after the code. It must pass. Records it.
#   scripts/gate.sh allow GLOB...                  more paths that count as verifier files (case-style globs).
#   scripts/gate.sh status                         print the state of this repo.
#   scripts/gate.sh off REASON                     allow every edit. Only when the user said to skip verifier-first.
#   scripts/gate.sh clear                          forget the state: the default (source edits denied) applies again.
#   scripts/gate.sh hook                           the PreToolUse hook. It reads the hook JSON on stdin.
#
# While the skill is active, SKILL.md registers `gate.sh hook` for Edit, Write, MultiEdit,
# NotebookEdit and Bash. Codex has no skill hooks: add `gate.sh hook` to ~/.codex/hooks.json for
# apply_patch and Bash (modes/build.md). With no open gate, a write to a file in the repo is denied, unless the file
# is a verifier file: a test, a spec, a fixture, formal/, *.lean, *.tla, *.cfg, *.md, or a verify
# skill. Writes outside the repo are never denied. For Bash the hook checks redirects, tee,
# sed -i, perl -i, patch and git apply. That is a best effort: it cannot see every program.
# State is per repo, in $UNDERSTANDO_STATE (default ~/.understando/gate), and expires after 12 hours.
# Needs jq for the hook.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_ROOT="${UNDERSTANDO_STATE:-$HOME/.understando/gate}"
usage() { sed -n '2,/^[^#]/{/^#/!d;s/^# \{0,1\}//;p;}' "$0"; }

repo_root() { git -C "${1:-.}" rev-parse --show-toplevel 2>/dev/null || (cd "${1:-.}" && pwd -P); }
set_root() { ROOT="$(repo_root "${1:-.}")"; D="$STATE_ROOT/$(printf '%s' "$ROOT" | shasum | cut -c1-12)"; }

# open | closed | off | none (none: no state, or the state is older than 12 hours)
state() {
  [ -f "$D/status" ] || { echo none; return; }
  [ -z "$(find "$D/status" -mmin +720 2>/dev/null)" ] && cat "$D/status" || echo none
}

# 0 when REL (a path relative to the repo root) is a verifier file.
verifier_path() {
  case "$1" in
    tests/*|*/tests/*|test/*|*/test/*|__tests__/*|*/__tests__/*|spec/*|*/spec/*|e2e/*|*/e2e/*) return 0 ;;
    formal/*|*/formal/*|fixtures/*|*/fixtures/*|docs/*|*/docs/*) return 0 ;;
    test_*|*/test_*|*_test.*|*.test.*|*.spec.*|conftest.py|*/conftest.py) return 0 ;;
    *.lean|*.tla|*.cfg|lakefile.*|*/lakefile.*|lean-toolchain|*.md) return 0 ;;
    .agents/skills/verify-*|.claude/skills/verify-*) return 0 ;;
  esac
  [ -f "$D/allow" ] || return 1
  while IFS= read -r g; do
    # shellcheck disable=SC2254
    case "$1" in $g) return 0 ;; esac
  done < "$D/allow"
  return 1
}

# A hash of the verifier files that differ from HEAD (changed or new).
vhash() {
  (cd "$ROOT" && git ls-files -m -o --exclude-standard 2>/dev/null | while IFS= read -r f; do
    verifier_path "$f" && [ -f "$f" ] && shasum "$f"
  done | shasum | cut -c1-12)
}

# Print the file argument of a Bash command that looks like a write, one per line.
bash_targets() {
  local c="$1" t s
  # Drop heredoc bodies and quoted text (commit messages, python -c, echo) so a ">" inside
  # them is not read as a redirect. A quoted target right after ">" or "tee" is kept, unquoted.
  s="$(printf '%s' "$c" | perl -0pe '
    s/(<<-?[ \t]*\\?(["\x27]?)(\w+)\2[^\n]*)\n.*?\n[ \t]*\3[ \t]*(?=\n|$)/$1/gs;
    s/((?:>>?|\btee(?:[ \t]+-a)?)[ \t]*)(?:"([^"\n]*)"|\x27([^\x27\n]*)\x27)|"(?:[^"\\]|\\.)*"|\x27[^\x27]*\x27/defined $1 ? $1.(defined $2 ? $2 : $3) : "\"\""/ges;
  ' 2>/dev/null)" || s="$c"
  {
    printf '%s' "$s" | grep -oE '(^|[^>0-9&])>>?[[:space:]]*[^[:space:];&|)>]+' | sed -E 's/^[^>]?>>?[[:space:]]*//'
    printf '%s' "$s" | grep -oE '(^|[^[:alnum:]_])tee( -a)?[[:space:]]+[^[:space:];&|)]+' | awk '{print $NF}'
  } | grep -vE '[`",()$]|^$'
  if printf '%s' "$s" | grep -qE '(sed|perl)[[:space:]]+-[a-zA-Z]*i|git apply|(^|[;&|[:space:]])patch[[:space:]]'; then
    for t in $(printf '%s' "$c" | tr ';&|' '   '); do
      t="${t%\'}"; t="${t#\'}"; t="${t%\"}"; t="${t#\"}"
      [ -f "$CWD/$t" ] || [ -f "$t" ] && echo "$t"
    done
  fi
}

# 0 when FILE is inside the repo and is not a verifier file.
guarded() {
  local f="$1" dir abs rel
  case "$f" in /*) ;; *) f="$CWD/$f" ;; esac
  dir="$(cd "$(dirname "$f")" 2>/dev/null && pwd -P)" || dir="$(dirname "$f")"
  abs="$dir/$(basename "$f")"
  case "$abs" in "$ROOT"/*) rel="${abs#"$ROOT"/}" ;; *) return 1 ;; esac
  verifier_path "$rel" && return 1
  return 0
}

deny() {
  jq -n --arg r "understando: write the verifier before the code. This change to $1 is blocked because no verifier has been seen to fail yet. Do this now: (1) ask the user the invariant: edge-case questions, no suggested answer; (2) run \`$HERE/gate.sh start \"<the invariant in the user's words>\"\`; (3) write the verifier (edits to tests, formal files, specs and verify skills are allowed); (4) run \`$HERE/gate.sh red -- <the verifier command>\`, or with \`--control\` for a behavior that exists already. The gate opens when the verifier fails for the right reason. If the user said to skip verifier-first, ask the user to confirm, then run \`$HERE/gate.sh off \"<reason>\"\`." \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $r}}'
  exit 0
}

hook() {
  command -v jq >/dev/null || { echo "understando gate: jq is missing, so the gate cannot check this edit" >&2; exit 0; }
  local in tool f
  in="$(cat)"
  tool="$(jq -r '.tool_name // ""' <<<"$in")"
  CWD="$(jq -r '.cwd // ""' <<<"$in")"; [ -n "$CWD" ] || CWD="$PWD"
  set_root "$CWD"
  case "$(state)" in open|off) exit 0 ;; esac
  case "$tool" in
    Edit|Write|MultiEdit) f="$(jq -r '.tool_input.file_path // empty' <<<"$in")" ;;
    NotebookEdit) f="$(jq -r '.tool_input.notebook_path // empty' <<<"$in")" ;;
    Bash) f="$(bash_targets "$(jq -r '.tool_input.command // ""' <<<"$in")")" ;;
    apply_patch) f="$(jq -r '.tool_input | (.command // .patch // .input // "") | tostring' <<<"$in" | sed -nE 's/^\*\*\* (Update|Add|Delete) File: //p')" ;;
    *) exit 0 ;;
  esac
  while IFS= read -r p; do
    [ -n "$p" ] && guarded "$p" && deny "${p#"$ROOT"/}"
  done <<<"$f"
  exit 0
}

# Run COMMAND; set CODE and OUT. A shell "not found" or "not executable" is not a verifier result.
run() {
  OUT="$("$@" 2>&1)"; CODE=$?
  if [ "$CODE" = 126 ] || [ "$CODE" = 127 ]; then echo "error: could not run \`$*\` (exit $CODE)"; printf '%s\n' "$OUT" | tail -n 5; exit 2; fi
}
tail_out() { printf '%s\n' "$OUT" | tail -n 15 | sed 's/^/  | /'; }
need_state() { [ "$(state)" != none ] || { echo "no gate for $ROOT: run \`gate.sh start \"<invariant>\"\` first" >&2; exit 2; }; }

CMD="${1:-}"; [ $# -gt 0 ] && shift
case "$CMD" in
  hook) hook ;;
  start)
    [ $# -ge 1 ] || { usage >&2; exit 2; }
    set_root; mkdir -p "$D"; rm -f "$D/red" "$D/green" "$D/vhash" "$D/reason"
    echo closed > "$D/status"; printf '%s\n' "$*" > "$D/invariant"
    echo "gate closed for $ROOT. Invariant: $*"
    echo "Write the verifier, then run: gate.sh red -- <the verifier command>" ;;
  red)
    set_root; need_state; CTL=()
    if [ "${1:-}" = --control ]; then
      shift; while [ $# -gt 0 ] && [ "$1" != -- ]; do CTL+=("$1"); shift; done
    fi
    [ "${1:-}" = -- ] && shift; [ $# -gt 0 ] || { usage >&2; exit 2; }
    if [ ${#CTL[@]} -gt 0 ]; then
      run "$HERE/control.sh" --dir "$ROOT" "${CTL[@]}" -- "$@"; tail_out
      [ "$CODE" = 2 ] && { echo "error: the bug could not be planted (see control.sh --help)"; exit 2; }
      [ "$CODE" = 0 ] && RED=1 || RED=
      WHAT="with a planted bug"
    else
      run "$@"; tail_out
      [ "$CODE" != 0 ] && RED=1 || RED=
      WHAT="on the current tree"
    fi
    if [ -z "$RED" ]; then
      echo "not red: \`$*\` did not fail $WHAT. A verifier that passes before the code exists tests nothing new."
      echo "Make it test the behavior that is missing. For a behavior that exists already, plant a bug with --control."
      exit 1
    fi
    printf '%s\t%s\t%s\n' "$(date +%FT%T)" "$*" "$WHAT" > "$D/red"; vhash > "$D/vhash"; echo open > "$D/status"
    echo "red: \`$*\` failed $WHAT. Check that the failure names the behavior, not a typo or a missing import. If it does not, fix the verifier and run red again."
    echo "gate open: source edits are allowed. Write the code, then run: gate.sh green -- <the verifier command>" ;;
  green)
    set_root; need_state
    [ "$(state)" = open ] || { echo "the gate is $(state): run \`gate.sh red\` first" >&2; exit 2; }
    [ "${1:-}" = -- ] && shift; [ $# -gt 0 ] || { usage >&2; exit 2; }
    run "$@"; tail_out
    [ "$CODE" = 0 ] || { echo "not green: \`$*\` exited $CODE. Write the code until the verifier passes."; exit 1; }
    printf '%s\t%s\n' "$(date +%FT%T)" "$*" > "$D/green"
    echo "green: \`$*\` passed."
    if [ "$(vhash)" != "$(cat "$D/vhash" 2>/dev/null)" ]; then
      echo "NOTE: a verifier file changed after it went red. Say so in the report, and run red again on the changed verifier against the code without the new change."
    fi
    echo "Next: run mutation testing on the changed functions (scripts/mutate.sh) and report each verifier with its control result." ;;
  allow)
    [ $# -ge 1 ] || { usage >&2; exit 2; }
    set_root; mkdir -p "$D"; printf '%s\n' "$@" >> "$D/allow"; echo "verifier globs for $ROOT: $*" ;;
  status)
    set_root; echo "repo:      $ROOT"; echo "gate:      $(state)"
    for f in invariant red green reason allow; do [ -f "$D/$f" ] && printf '%-10s %s\n' "$f:" "$(tr '\n' ' ' < "$D/$f")"; done; exit 0 ;;
  off)
    [ $# -ge 1 ] || { usage >&2; exit 2; }
    set_root; mkdir -p "$D"; echo off > "$D/status"; printf '%s\n' "$*" > "$D/reason"
    echo "gate off for $ROOT: every edit is allowed. Reason: $*" ;;
  clear) set_root; rm -rf "$D"; echo "gate cleared for $ROOT: source edits are denied until a verifier fails." ;;
  -h|--help|"") usage; [ -n "$CMD" ] || exit 2; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
