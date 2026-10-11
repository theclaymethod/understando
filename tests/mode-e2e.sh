#!/usr/bin/env bash
# The mode e2e: tests/e2e.sh calls it after the base run, with WORK, REPO, MAP, HEAD and FIX set.
# It drives the understando CLI on the fixture in a fake HOME that holds only the required skills
# (asd-ste100 and visual-explainer), so every optional route falls back to an adapted copy or a
# built-in rule. No model call, no network.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
U="$ROOT/bin/understando"
REAL_HOME="$HOME"
RUN="$WORK/run"
step() { printf '\n== %s\n' "$*"; }
fail() { echo "FAIL: $*"; exit 1; }
has() { grep -qF -- "$2" "$1" || { echo "--- $1"; cat "$1"; fail "$1 lacks: $2"; }; }
lacks() { if grep -qF -- "$2" "$1"; then fail "$1 holds: $2"; fi; }
real_skill() { for d in "$REAL_HOME/.agents/skills/$1" "$REAL_HOME/.claude/skills/$1"; do [ -f "$d/SKILL.md" ] && { readlink -f "$d"; return; }; done; fail "the required skill $1 is not installed"; }

FH="$WORK/home"
mkdir -p "$FH/.agents/skills" "$FH/.claude/skills"
for s in asd-ste100 visual-explainer; do p="$(real_skill "$s")"; ln -s "$p" "$FH/.agents/skills/$s"; ln -s "$p" "$FH/.claude/skills/$s"; done
export npm_config_cache="${npm_config_cache:-$REAL_HOME/.npm}"
export HOME="$FH" UNDERSTANDO_HOME="$WORK/uhome" UNDERSTANDO_OFFLINE=1 UNDERSTANDO_ENV_FILES="$WORK/fake.env"
mkdir -p "$RUN"
cp "$MAP" "$RUN/trust-map.json"
cp "$FIX/explain.json" "$RUN/explain.json"
cp "$FIX/explainer.mdx" "$RUN/explainer.mdx"
O="$WORK/out"; mkdir -p "$O"

step "setup: the skill links and the CLI link, in the fake HOME"
bash "$ROOT/scripts/setup.sh" --links-only > "$O/setup.txt"
for d in .agents .claude .codex .cursor; do
  test "$(readlink "$FH/$d/skills/understando")" = "$ROOT" || fail "no link $FH/$d/skills/understando"
done
test "$(readlink "$FH/.local/bin/understando")" = "$ROOT/bin/understando" || fail "no CLI link"
for d in .agents .claude .codex .cursor; do
  l="$REAL_HOME/$d/skills/understando"
  if [ -e "$l" ] && ! grep -q '^name: understando$' "$l/SKILL.md" 2>/dev/null; then fail "$l holds another skill"; fi
  [ -e "$l" ] && echo "real link ok: $l -> $(readlink -f "$l")" || echo "real link absent: $l (run setup)"
done

step "portability: the router text names no Claude-only tool, and the CLI runs without Claude"
TOOLS='\b(AskUserQuestion|AskQuestion|TodoWrite|WebFetch|WebSearch|NotebookEdit|ExitPlanMode|SlashCommand|subagent_type|run_in_background)\b|\b(Task|Bash|Read|Edit|Write|Grep|Glob|Agent|Skill) tool\b'
if grep -nE "$TOOLS" "$ROOT/SKILL.md" "$ROOT"/commands/*.md "$ROOT/references/working-rules.md"; then fail "the router names a Claude-only tool"; fi
NOCLAUDE="$(dirname "$(command -v git)"):$(dirname "$(command -v python3)"):/usr/bin:/bin"
env -i HOME="$FH" PATH="$NOCLAUDE" UNDERSTANDO_HOME="$WORK/uhome" UNDERSTANDO_OFFLINE=1 bash -c '! command -v claude >/dev/null' \
  || fail "claude is on the stripped PATH"
env -i HOME="$FH" PATH="$NOCLAUDE" UNDERSTANDO_HOME="$WORK/uhome" UNDERSTANDO_OFFLINE=1 "$U" --run "$RUN" signals > "$O/signals-noclaude.json"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["trust_map"]["present"], d' "$O/signals-noclaude.json"
echo "the CLI runs with no claude binary and no Claude variable"

python3 "$ROOT/scripts/gen_router.py" --check

step "mode: off, then on, then status"
"$U" mode status > "$O/mode0.txt"; has "$O/mode0.txt" "understando mode: off"
"$U" --run "$RUN" --repo "$REPO" --pr 1 mode on > "$O/mode1.txt"; has "$O/mode1.txt" "understando mode: on"
"$U" --json mode status > "$O/mode2.json"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["on"] and d["run"].endswith("/run") and str(d["pr"]) == "1", d' "$O/mode2.json"

step "bare menu: one question with two or three picks; the verb table only on --all"
"$U" > "$O/menu.txt"
has "$O/menu.txt" "What next?"; has "$O/menu.txt" "  1. "; has "$O/menu.txt" " (recommended): "; has "$O/menu.txt" "Something else"
lacks "$O/menu.txt" "Get ready"; lacks "$O/menu.txt" "Aliases:"
test "$(grep -cE '^  [0-9]\. ' "$O/menu.txt")" -le 4 || fail "the menu has more than 4 options"
"$U" menu --all > "$O/menu-all.txt"; has "$O/menu-all.txt" "Get ready"; has "$O/menu-all.txt" "Aliases:"
"$U" --json menu > "$O/menu.json"
python3 - "$O/menu.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
picks = [p["verb"] for p in d["recommend"]]
assert 2 <= len(picks) <= 3, picks
assert "learn" not in picks, "learn is paused"
sig = d["signals"]
if sum(len(v) for v in sig["open_claims"].values()):
    assert "close" in picks or len(picks) == 3, picks
assert sig["discover"]["candidates"] == 0 and picks[0] == "discover", picks
print("menu picks:", picks)
PY

step "deprecated aliases print the new verb"
"$U" controls --help > /dev/null 2> "$O/alias1.txt"; has "$O/alias1.txt" 'deprecated: use `understando probe`'
"$U" rerun --help > /dev/null 2> "$O/alias2.txt"; has "$O/alias2.txt" 'deprecated: use `understando map`'

step "note: the ledger redacts a planted key, a bearer token and an .env value"
printf 'FAKE_SERVICE_TOKEN=fakeEnvValue0123456789\n' > "$WORK/fake.env"
"$U" note prompt "Use sk-fake0000111122223333444455556666 with Bearer abcdefghijklmnopqrstuvwxyz and fakeEnvValue0123456789 to test the fee." > /dev/null
for secret in sk-fake0000111122223333444455556666 abcdefghijklmnopqrstuvwxyz fakeEnvValue0123456789; do
  if grep -q "$secret" "$RUN/journal.jsonl"; then fail "the journal holds a planted secret"; fi
done
test "$(grep -o 'REDACTED' "$RUN/journal.jsonl" | wc -l | tr -d ' ')" -ge 3 || fail "fewer than three redactions"
echo "3 planted secrets are redacted"
"$U" note prompt "Make sure the fee is right for each amount, and that the wallet refuses an overdraft." --claims C03,C01 > /dev/null
echo '{"prompt": "Keep the PR small, and prove each check can fail."}' | "$U" hook user-prompt
echo '{"prompt": "Keep the PR small, and prove each check can fail."}' | "$U" hook user-prompt
test "$(grep -c '"source": "hook"' "$RUN/journal.jsonl")" = 1 || fail "the hook row is missing, or the duplicate was kept"
"$U" note --export-tsv > /dev/null
test "$(head -1 "$RUN/decisions.tsv")" = "$(printf 'ts\tphase\tdecision\twhy\tevidence\tresult')" || fail "the TSV header differs"

step "discover: one accept, one reword, one reject, one answer that contradicts the code, one agent pick"
"$U" discover > "$O/discover0.txt"; has "$O/discover0.txt" "candidates"
"$U" discover questions > "$O/questions.txt"; has "$O/questions.txt" "What should happen if amount is exactly equal to balance?"
python3 - "$RUN/discover.json" "$WORK/discover-answers.json" <<'PY'
import json, sys
st = json.load(open(sys.argv[1]))
find = lambda p: next(c["id"] for c in st["candidates"] if c["text"].startswith(p))
json.dump({"answers": [
    {"candidate": find("withdraw: when amount > balance"), "decision": "accept", "confirmed": True,
     "examples": [{"question": "What should happen if amount is above balance?", "expr": "withdraw(10, 11)", "raises": "OverdraftError"}],
     "frog": {"risk": 3, "impact": 3, "effort": 1}},
    {"candidate": find("fee returns"), "decision": "reword", "confirmed": True, "claims": ["C03"],
     "text": "The fee is one, plus one for each full hundred of the amount.",
     "examples": [{"question": "What should fee give when amount is 250?", "expr": "fee(250)", "expect": "3"}]},
    {"candidate": find("denial returns"), "decision": "reject", "reason": "The message text is copy, not a rule."},
    {"candidate": find("withdraw returns"), "decision": "accept", "confirmed": True,
     "rating": {"priority": "P1", "fix": "Small", "finding_confidence": 95, "fix_confidence": 90,
                "fix_direction": "Refuse an amount below zero before the balance check."},
     "examples": [{"question": "What should withdraw do when amount is below zero?", "expr": "withdraw(10, -5)", "raises": "ValueError"}]},
    {"candidate": find("The wallet module is safe"), "decision": "accept"}],
  "rest": {"decision": "defer", "reason": "Not in scope for this review."}}, open(sys.argv[2], "w"))
PY
"$U" discover answer --answers "$WORK/discover-answers.json" > "$O/discover1.txt"
has "$O/discover1.txt" "reword as I02 (accepted, author user"
has "$O/discover1.txt" "reject: The message text is copy, not a rule."
# A bug finding renders in the find-bugs format: the rating in the heading, then the trigger, expected and actual, and the evidence.
has "$O/discover1.txt" "P1 — [Small fix, 95% finding confidence, 90% fix confidence] "
has "$O/discover1.txt" "  Trigger: What should withdraw do when amount is below zero?"
has "$O/discover1.txt" "  Expected: raises ValueError. Actual: 15."
has "$O/discover1.txt" "  Fix: Refuse an amount below zero before the balance check."
has "$O/discover1.txt" "  Evidence: "
has "$O/discover1.txt" "PROPOSED: no user confirm"
has "$O/discover1.txt" "DONE: every candidate has a decision."
AGENT_INV="$(python3 -c 'import json,sys; print(next(i["id"] for i in json.load(open(sys.argv[1]))["invariants"] if i["author"] == "agent"))' "$RUN/trust-map.json")"
python3 - "$RUN/journal.jsonl" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
inv = [r for r in rows if r["kind"] == "invariant"]
assert any(r.get("author") == "user" and r["what"].startswith("The fee is one") and r.get("status") == "accepted" for r in inv), inv
assert any(r.get("status") == "rejected" and r.get("reason") for r in inv)
assert any(r.get("possible_bug") for r in inv)
print(f"{len(inv)} invariant rows; the reword, the rejection and the possible bug are in the journal")
PY
if "$U" build claim --invariant "$AGENT_INV" > "$O/refuse1.txt" 2>&1; then fail "build accepted an unconfirmed invariant"; fi
has "$O/refuse1.txt" "refuse:"
if "$U" formalize --invariant "$AGENT_INV" > "$O/refuse2.txt" 2>&1; then fail "formalize accepted an unconfirmed invariant"; fi
has "$O/refuse2.txt" "refuse:"
echo "build and formalize refuse the unconfirmed invariant $AGENT_INV"

step "close: an e2e test closes the Gap, a property test replaces the weak check of an Asserted claim, one waiver"
"$U" close --list > "$O/queue.txt"
test "$(head -1 "$O/queue.txt" | cut -d' ' -f1-2)" = "C03 Gap:" || fail "the riskiest claim is not first"
"$U" close --answers "$FIX/ready/close-answers.json" > "$O/close.txt"
has "$O/close.txt" "C03: V11 goes green, and red on control K09"
has "$O/close.txt" "C02: V12 goes green, and red on control K10. It replaces V02."
has "$O/close.txt" "C04: waived"
has "$O/close.txt" "DONE: every claim is Formal, Proven, Backed or waived."
git -C "$REPO" rev-parse -q --verify refs/heads/understando/1-ready > /dev/null || fail "no ready branch"
test "$(git -C "$REPO" rev-parse main)" = "$HEAD" || fail "close changed the PR's own commits"

step "trim: the redundant unit test goes, the unique one stays, flagged for conversion"
"$U" trim > "$O/trim.txt"
has "$O/trim.txt" "deleted V01 (tests/test_core.py:OverdraftTest)"
has "$O/trim.txt" "keep V07: convert to e2e first"
has "$O/trim.txt" "excess or untested bin/report.py:main"
has "$O/trim.txt" "protected wallet/core.py:withdraw"
git -C "$REPO" show understando/1-ready:tests/test_core.py > "$O/test_core.py"
lacks "$O/test_core.py" "class OverdraftTest"
git -C "$REPO" show understando/1-ready:tests/test_messages.py | grep -q "class DenialTest" || fail "trim deleted the unique unit test"
python3 - "$RUN/trust-map.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
v = {c["id"]: (c["verdict"], c.get("tier")) for c in d["claims"]}
assert "V01" not in {x["id"] for x in d["verifiers"]}
assert v["C01"][0] == "Proven" and v["C03"] == ("Proven", 1) and v["C02"] == ("Proven", 2), v
assert v["C08"] == ("Formal", 5), v
print("after trim:", v)
PY

step "ready --report: the four gates; gate 1 uses the evidence bars"
# With the default bars, the unit-tested claims are below the backend bar, and gate 1 fails.
"$U" ready --report > "$O/ready-bars.txt" || true
has "$O/ready-bars.txt" "gate 1 at its bar: fail"
has "$O/ready-bars.txt" "below the bar with no waiver"
# The per-repo config lowers the bars of this small fixture: a test that caught its bug is enough.
CFGNAME="$(python3 -c 'import sys, pathlib; sys.path.insert(0, sys.argv[1]); import repoinfo; print(repoinfo.repo_name(pathlib.Path(sys.argv[2])))' "$ROOT/scripts" "$REPO")"
mkdir -p "$UNDERSTANDO_HOME/runs/$CFGNAME"
printf '\n[bars.backend]\nnormal = "test"\n[bars.llm]\nnormal = "check"\n[bars.other]\nnormal = "check"\n' >> "$UNDERSTANDO_HOME/runs/$CFGNAME/understando.toml"
"$U" ready --report > "$O/ready.txt"
for g in "gate 1 at its bar: pass" "gate 2 no excess code: fail" "gate 3 no unit test that an e2e test covers: pass" "gate 4 explainable: pass" "Independent review" "references/adapted/autoreview.md" "a self-review is not independent"; do
  has "$O/ready.txt" "$g"
done

step "explain: the checklist on top of the PR section, the glossary file, the pre-rendered page"
"$U" explain > "$O/explain.txt"
has "$RUN/explainer.html" 'data-ve-trust="merge"'
has "$RUN/explainer.html" "Why it was built this way"
has "$RUN/pr-section.md" "### Ready checklist"
has "$RUN/pr-section.md" "**Formal**"
has "$RUN/pr-section.md" "waived: The wallet keeps no shared state"
has "$RUN/GLOSSARY.md" "**Overdraft**:"
test -f "$RUN/explain.stamp.json" || fail "explain wrote no stamp"

step "routes: no originals in the fake HOME, so each route uses an adapted copy or a built-in rule"
"$U" --json routes > "$O/routes.json"
python3 - "$O/routes.json" "$ROOT" <<'PY'
import json, pathlib, re, sys
rows, root = json.load(open(sys.argv[1]))["routes"], pathlib.Path(sys.argv[2])
manifest = json.load(open(root / "references/adapted/manifest.json"))
originals = {m["original_skill"] for m in manifest}
for r in rows:
    if r.get("required"):
        continue
    assert r["use"] in ("adapted", "built-in"), r
    if r["skill"] in originals:
        assert r["use"] == "adapted", r
for m in manifest:
    head = (root / m["file"]).read_text().split("-->", 1)[0]
    for field in ("adapted-from:", "source:", "source-version:", "license: MIT", "original-skill:"):
        assert field in head, (m["file"], field)
router = (root / "SKILL.md").read_text() + (root / "references/working-rules.md").read_text()
missing = [r["skill"] for r in json.load(open(root / "commands.json"))["routes"] if r["skill"] not in router]
assert not missing, f"the router does not name {missing}"
print(f"{sum(r['use'] == 'adapted' for r in rows)} routes use an adapted copy; {len(manifest)} adapted files carry the source and licence header")
PY
"$U" --json doctor > "$O/doctor.json"
python3 - "$O/doctor.json" <<'PY'
import json, sys
f = {x["id"]: x for x in json.load(open(sys.argv[1]))["findings"]}
for name in ("grilling", "unslop", "principle-prove-it-works", "simplify"):
    assert f[f"skill-{name}"]["severity"] == "mention", f.get(f"skill-{name}")
assert not [x for x in f.values() if x["id"].startswith("skill-") and x["severity"] != "mention"], "a missing optional skill is not a mention"
print("doctor lists each missing optional skill as a mention")
PY
FH2="$WORK/home2"
mkdir -p "$FH2/.agents/skills/principle-prove-it-works" "$FH2/.agents/skills/unslop"
printf -- '---\nname: principle-prove-it-works\ndescription: stub\n---\n' > "$FH2/.agents/skills/principle-prove-it-works/SKILL.md"
printf -- '---\nname: unslop\ndescription: stub\n---\n' > "$FH2/.agents/skills/unslop/SKILL.md"
HOME="$FH2" "$U" routes > "$O/routes2.txt"
grep -E "^principle-prove-it-works +skill principle-prove-it-works" "$O/routes2.txt" > /dev/null || fail "no route to the installed principle-prove-it-works"
grep -E "^unslop +skill unslop" "$O/routes2.txt" > /dev/null || fail "no route to the installed unslop"
echo "with the originals installed, the routes go to them"

step "Poteto Mode active: understando defers to its reply rules, except discover, claim wording and waivers"
"$U" --run "$RUN" --repo "$REPO" --pr 1 mode on --with poteto-mode > /dev/null
"$U" routes > "$O/routes3.txt"
head -1 "$O/routes3.txt" | grep -q "poteto-mode is active: it owns the reply style, the subagent rules and autonomy. understando defers to it, except: discover, claim wording and waivers stop for the user." \
  || fail "no defer line"
"$U" --run "$RUN" --repo "$REPO" --pr 1 mode on > /dev/null

step "autonomy: an agent-picked invariant caps its claim at Backed"
RUN2="$WORK/run2"; cp -R "$RUN" "$RUN2"
python3 - "$RUN2/trust-map.json" "$AGENT_INV" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
next(c for c in d["claims"] if c["id"] == "C03")["invariant"] = sys.argv[2]
json.dump(d, open(sys.argv[1], "w"), indent=2)
PY
"$U" --run "$RUN2" map > "$O/map2.txt"
python3 - "$RUN2/trust-map.json" <<'PY'
import json, sys
c = next(c for c in json.load(open(sys.argv[1]))["claims"] if c["id"] == "C03")
assert c["verdict"] == "Backed" and "confirmed" in c["reason"], c
print("C03 with an agent-picked invariant:", c["verdict"])
PY
UNDERSTANDO_AUTONOMY=1 "$U" --run "$RUN2" build claim --invariant "$AGENT_INV" > "$O/auto.txt" || fail "full autonomy refused an agent invariant"

step "doctor flags a deleted @cc comment, and an import with a bad format is stale"
CL="$WORK/cc-clone"
git clone -q "$REPO" "$CL"
sed -i.bak '/@cc /d' "$CL/wallet/core.py" && rm "$CL/wallet/core.py.bak"
git -C "$CL" -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false commit -q -am "drop the contract line"
git -C "$CL" push -q origin HEAD:refs/heads/cc-test
CC="$(git -C "$REPO" rev-parse cc-test)"
python3 - "$RUN2/trust-map.json" "$CC" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d["ready"] = {"branch": "cc-test", "head": sys.argv[2]}
json.dump(d, open(sys.argv[1], "w"), indent=2)
PY
printf 'when\twhat\n2026-10-10\tsomething\n' > "$WORK/bad.tsv"
"$U" --run "$RUN2" import show-me-your-work "$WORK/bad.tsv" --claim C05 --description "A decision log for the message review." > "$O/import.txt"
has "$O/import.txt" "STALE"
"$U" --run "$RUN2" import show-me-your-work "$RUN/decisions.tsv" --claim C05 --description "The decision log of this run." > "$O/import2.txt"
has "$O/import2.txt" " is ok "
"$U" --run "$RUN2" --json doctor > "$O/doctor2.json"
python3 - "$O/doctor2.json" <<'PY'
import json, sys
f = json.load(open(sys.argv[1]))["findings"]
assert any(x["id"] == "cc-deleted-ready" for x in f), [x["id"] for x in f]
assert any(x["id"].startswith("import-stale-") for x in f), [x["id"] for x in f]
print("doctor: cc-deleted-ready and import-stale")
PY
git -C "$REPO" branch -q -D cc-test

step "discover import: a formal sidecar's proposed invariants, then the user's decisions rate the record"
SIDE="$RUN2/formal/verifiers.json"; mkdir -p "$RUN2/formal"; cp "$FIX/ready/sidecar.json" "$SIDE"
"$U" --run "$RUN2" formalize --sidecar "$SIDE" > "$O/side0.txt"
has "$O/side0.txt" "FW1: Formal (pending user confirmation)"
"$U" --run "$RUN2" discover import --sidecar "$SIDE" > "$O/side1.txt"
has "$O/side1.txt" "W1, W1-q2"
"$U" --run "$RUN2" discover questions > "$O/side2.txt"
has "$O/side2.txt" "code today: It pays out a negative amount"
printf '%s' '{"answers": [{"candidate": "W1", "decision": "accept", "confirmed": true, "claims": ["C01"]},
  {"candidate": "W1-q2", "decision": "defer", "reason": "The owner decides negative amounts.", "owner": "wallet team"}]}' > "$WORK/side-answers.json"
"$U" --run "$RUN2" discover answer --answers "$WORK/side-answers.json" > "$O/side3.txt"
has "$O/side3.txt" "Owner: wallet team."
"$U" --run "$RUN2" formalize --sidecar "$SIDE" > "$O/side4.txt"
has "$O/side4.txt" "FW1: Formal"
lacks "$O/side4.txt" "FW1: Formal (pending"
python3 - "$RUN2/trust-map.json" "$SIDE" <<'PY'
import json, sys
d, side = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
c = {x["id"]: x for x in d["claims"]}
# A part is as strong as its strongest check: the Formal record makes the claim Formal, and the tests next to it do not lower it.
assert c["C01"]["verdict"] == "Formal" and c["C01"]["tier"] == 5 and "FW1" in c["C01"]["checks"], c["C01"]
dup = [x for x in d["claims"] if x["source"].endswith("(formal FCW1)")]
assert not dup, "the duplicate proposed claim was added"
assert any(x["source"].endswith("(formal FCW2)") for x in d["claims"]), "the new proposed claim is missing"
assert side["verifiers"][0]["invariant"]["author"] == "user"
assert next(i for i in d["invariants"] if i["id"] == "W1-q2")["status"] == "proposed"
print("the sidecar record is Formal after the user confirmed W1; the deferred question stays proposed")
PY

step "review: the context from the PR number alone, with a fake gh, a fixture workflow and a fixture understando.toml"
RV="$WORK/rv"; mkdir -p "$RV/bin"
export UNDERSTANDO_RUNS="$WORK/runs"
rg() { git -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false "$@"; }
git clone -q --bare "$REPO" "$RV/wallet.git"
git -C "$RV/wallet.git" for-each-ref --format='%(refname)' refs/heads/understando | while read -r ref; do git -C "$RV/wallet.git" update-ref -d "$ref"; done
SEED="$RV/seed"; git clone -q "$RV/wallet.git" "$SEED"
mkdir -p "$SEED/.github/workflows" "$SEED/wallet/private"
cat > "$SEED/.github/workflows/ci.yml" <<'YML'
name: CI
on:
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: Tests
        run: python3 -m unittest -q
      - name: Needs CI context
        run: echo "${{ github.sha }}"
YML
CANARY="understando-canary-7731"
printf 'TOKEN=%s\n' "$CANARY" > "$SEED/wallet/.env.local"
mkdir -p "$SEED/formal"; printf '{"amount": 1, "fee": 1}\n' > "$SEED/formal/fee_vectors.jsonl"
printf '"""Planted secret: understando must never read this file."""\n\n\n# @cc wallet.private.hook\ndef hook(x: int) -> int:\n    if x > 7731:\n        raise ValueError("%s")\n    return x\n' "$CANARY" > "$SEED/wallet/private/hook.py"
rg -C "$SEED" add -A && rg -C "$SEED" commit -q -m "CI workflow and a planted secret"
PR_HEAD="$(git -C "$SEED" rev-parse HEAD)"
rg -C "$SEED" push -q origin HEAD:main
rg -C "$SEED" push -q origin "HEAD:refs/heads/understando/1-ready"
echo "$PR_HEAD" > "$RV/head"
cat > "$RV/bin/gh" <<GH
#!/usr/bin/env bash
echo "\$*" >> "$RV/gh.log"
if [ "\$1 \$2" = "pr view" ]; then
  case " \$* " in *" -q "*) cat "$RV/head"; exit 0 ;; esac
  printf '{"headRefOid":"%s","baseRefName":"main","state":"OPEN","title":"Refuse overdrafts"}\n' "\$(cat "$RV/head")"
  exit 0
fi
echo "fake gh refuses: \$*" >&2; exit 3
GH
chmod +x "$RV/bin/gh"
export PATH="$RV/bin:$PATH"
CL="$RV/wallet"; git clone -q "$RV/wallet.git" "$CL"
R="$UNDERSTANDO_RUNS/wallet/1"; mkdir -p "$R"
sed "s/$HEAD/$PR_HEAD/g" "$MAP" > "$R/trust-map.json"
cp "$FIX/explain.json" "$R/explain.json"
cp "$FIX/explainer.mdx" "$R/explainer.mdx"
cat > "$UNDERSTANDO_RUNS/wallet/understando.toml" <<'TOML'
schema = "understando.repo/1"
repo = "fixture/wallet"
budget_usd = 0
secret_paths = ["**/.env*", "wallet/private/**"]
[[protected_paths]]
path = "bin/"
owner = "Ops team"
reason = "The ops team owns the report script."
[deferred_owners]
[bars.backend]
normal = "test"
[bars.llm]
normal = "check"
[bars.other]
normal = "check"
TOML
(cd "$CL" && "$U" review 1 --json) > "$O/review1.json"
python3 - "$O/review1.json" "$R" "$CL" <<'PY'
import json, os, sys
d, run, cl = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
assert os.path.realpath(d["run"]) == os.path.realpath(run), d["run"]
wt = os.path.join(cl, ".claude/worktrees/understando-1-ready")
assert os.path.realpath(d["worktree"]) == os.path.realpath(wt) and os.path.isdir(wt), d["worktree"]
assert d["stopped"] == "before map" and d["next"] == "map" and d["awaiting"] == "go", (d["stopped"], d["next"])
assert d["ci"]["present"] and not d["ci"]["approved"], d["ci"]
ci = json.load(open(os.path.join(run, "ci.json")))
cmd = [c for c in ci["commands"] if c.get("argv") == ["python3", "-m", "unittest", "-q"]]
assert cmd and cmd[0]["source"] == ".github/workflows/ci.yml:10" and cmd[0]["job"] == "test", ci["commands"]
assert any("CI expression" in e["excluded"] for e in ci["excluded"]), ci["excluded"]
assert ci["approval"] is None
assert d["verdicts"] and isinstance(d["open"], list) and "gates" in d
print("review resolves the run, makes the ready worktree, writes ci.json from the workflow, and stops before map")
PY
test -f "$R/review.json" || fail "no review.json"
test "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["on"])' "$UNDERSTANDO_HOME/mode.json")" = True || fail "review did not turn the mode on"

step "review: the menu offers review for the open PR of the cwd"
(cd "$CL" && env -u UNDERSTANDO_OFFLINE "$U" --json menu) > "$O/menu-review.json"
python3 -c 'import json,sys; p=json.load(open(sys.argv[1]))["recommend"]; assert p[0]["command"] == "understando review 1", p' "$O/menu-review.json"

step "review: a remote ready branch that is ahead; the guard refuses, then review pulls with --no-rebase"
WT="$CL/.claude/worktrees/understando-1-ready"
OTHER="$RV/other"; git clone -q -b understando/1-ready "$RV/wallet.git" "$OTHER"
printf '# a note from another agent\n' >> "$OTHER/wallet/fees.py"
rg -C "$OTHER" commit -q -am "another agent: a note in fees.py"
rg -C "$OTHER" push -q origin HEAD:understando/1-ready
AHEAD="$(git -C "$OTHER" rev-parse HEAD)"
if (cd "$CL" && "$U" review 1 --guard wallet/core.py) > "$O/guard1.txt"; then fail "the guard allowed an edit with unpulled commits"; fi
has "$O/guard1.txt" "has 1 commits on origin that"
(cd "$CL" && "$U" review 1 --json) > "$O/review2.json"
python3 - "$O/review2.json" "$AHEAD" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["pulled"] and d["pulled"]["commits"] == 1 and d["pulled"]["to"] == sys.argv[2], d["pulled"]
assert d["ready_tip"] == sys.argv[2]
assert "C03" in d["reverify"]["claims"], d["reverify"]
print("review pulled 1 commit; it offers C03 to verify again")
PY
test "$(git -C "$WT" rev-parse HEAD)" = "$AHEAD" || fail "the worktree did not pull"
(cd "$CL" && "$U" review 1 --guard wallet/core.py) > "$O/guard2.txt" || fail "the guard refused after the pull"
if (cd "$CL" && "$U" review 1 --guard bin/report.py) > "$O/guard3.txt"; then fail "the guard allowed a protected path"; fi
has "$O/guard3.txt" "refuse: bin/report.py is protected (owner Ops team"
if (cd "$CL" && "$U" review 1 --guard wallet/.env.local) > "$O/guard4.txt"; then fail "the guard allowed a secret path"; fi
has "$O/guard4.txt" "is a secret path"

step "review: --go stops while the CI profile is not approved"
(cd "$CL" && "$U" review 1 --go) > "$O/review3.txt"
has "$O/review3.txt" "Approve the CI profile?"
if "$U" --run "$R" --repo "$CL" probe > "$O/probe-noci.txt"; then fail "probe ran with an unapproved CI profile"; fi
has "$O/probe-noci.txt" "refuse: the CI profile is not approved"

step "review prompt: one question, at most 5 situation lines, at most 4 options, a cost and a time, no verb table"
(cd "$CL" && "$U" review 1 --json) > "$O/review-prompt.json"
(cd "$CL" && "$U" review 1) > "$O/review-prompt.txt"
python3 - "$O/review-prompt.json" "$O/review-prompt.txt" "$ROOT" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))["prompt"]
text = open(sys.argv[2]).read()
assert 1 <= len(p["situation"]) <= 5, p["situation"]
assert 2 <= len(p["options"]) <= 4, p["options"]
assert p["options"][0].get("recommended") and p["options"][-1]["label"] == "Something else", p["options"]
assert "  1. " + p["options"][0]["label"] + " (recommended): " in text, text
assert p["next"]["cost"].startswith("$") and p["next"]["time"], p["next"]
assert p["next"]["scope"] and p["next"]["writes"], p["next"]
assert p["question"] in text and "Next: " in text and "Cost: $" in text and "Time: " in text, text
for word in ("Get ready", "Aliases:", "| Verb |", "Understand\n", "  discover  "):
    assert word not in text, word
assert len(text.strip().splitlines()) <= 5 + 2 + 2 + 4, text
# Plain names only: no bare ID, SHA or path:line in the words that the user reads.
import re, sys as _s
_s.path.insert(0, sys.argv[3] + "/scripts")
import prompt as P
bad = [x for t in P.user_texts(p) for x in P.plain_problems(t)]
assert not bad, bad
for line in p["situation"]:
    assert not re.search(r"\b[0-9a-f]{7,40}\b", line) and not re.search(r"\.\w+:\d+", line) and "selector" not in line, line
print(f"review: {len(p['situation'])} situation lines, {len(p['options'])} options, cost {p['next']['cost']!r}, time {p['next']['time']!r}")
PY

step "lock: a second writer on an overlapping path is refused; a free path is not"
sleep 60 & P1=$!
sleep 60 & P2=$!
"$U" --run "$R" lock take --verb formalize --paths ready:wallet/ --pid "$P1" --owner agent-a > "$O/lock1.txt"
if "$U" --run "$R" lock take --verb close --paths ready:wallet/core.py --pid "$P2" --owner agent-b > "$O/lock2.txt"; then fail "the lock let a second writer in"; fi
has "$O/lock2.txt" "refuse: agent-a holds the run lock for \`formalize\` (pid $P1"
"$U" --run "$R" lock take --verb trim --paths ready:tests/ --pid "$P2" --owner agent-b > "$O/lock3.txt" || fail "the lock refused a free path"
if (cd "$CL" && "$U" review 1 --guard wallet/core.py) > "$O/guard5.txt"; then fail "the guard ignored a live lock"; fi
has "$O/guard5.txt" "agent-a holds the run lock"
if "$U" --run "$R" --repo "$CL" close --answers "$FIX/ready/close-answers.json" > "$O/close-locked.txt"; then fail "close ran under a live lock"; fi
has "$O/close-locked.txt" "refuse: agent-"
kill "$P1" "$P2"; wait "$P1" "$P2" 2>/dev/null || true
"$U" --run "$R" lock status > "$O/lock4.txt"; has "$O/lock4.txt" "lock: free"

step "secret paths: discover and a mechanical grep never read them"
"$U" --run "$R" --repo "$CL" discover > /dev/null
python3 - "$R" "$CL" "$PR_HEAD" "$CANARY" "$ROOT" <<'PY'
import json, sys
run, cl, head, canary, root = sys.argv[1:6]
sys.path.insert(0, root + "/scripts")
import mechanical
assert canary not in open(run + "/discover.json").read(), "discover read a secret file"
r = mechanical.run(cl, head, head, {"op": "grep-present", "pattern": canary, "paths": ["wallet/"]})
assert r["status"] == "fail" and "No match" in r["detail"], r
print("discover and git grep skip the secret paths")
PY
python3 - "$R/discover.json" "$WORK/discover-answers-r.json" <<'PY'
import json, sys
st = json.load(open(sys.argv[1]))
fee = next(c["id"] for c in st["candidates"] if c["text"].startswith("fee returns"))
json.dump({"answers": [{"candidate": fee, "decision": "reword", "confirmed": True, "claims": ["C03"],
                        "text": "The fee is one, plus one for each full hundred of the amount."}],
           "rest": {"decision": "defer", "reason": "Not in scope for this review.", "owner": "wallet team"}}, open(sys.argv[2], "w"))
PY
"$U" --run "$R" --repo "$CL" discover answer --answers "$WORK/discover-answers-r.json" > /dev/null

step "review: a go runs map + probe as one stop, then close asks about one claim only"
printf '{"ci": "approve"}' > "$WORK/ci-yes.json"
(cd "$CL" && "$U" review 1 --answers "$WORK/ci-yes.json") > "$O/ci-yes.txt"
has "$O/ci-yes.txt" "Run map + probe on the changed code?"
(cd "$CL" && "$U" review 1 --go) > "$O/go-check.txt" 2>&1 || { tail -30 "$O/go-check.txt"; fail "the check stop failed"; }
has "$O/go-check.txt" "Map: the verdicts are up to date at the review-branch tip ✓"; has "$O/go-check.txt" "== review: probe"
test -s "$R/logs/review-map.log" || fail "the map output is not in the run log"
lacks "$O/go-check.txt" "== review: trim"
(cd "$CL" && "$U" review 1 --json) > "$O/close-prompt.json"
python3 - "$O/close-prompt.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
p = d["prompt"]
others = [o["id"] for o in d["open"] if o["id"] != p["claim"]]
assert p["claim"] in [o["id"] for o in d["open"]], p
assert p["question"].startswith("How do we close '") and p["claim"] not in p["question"], p["question"]
shown = json.dumps([p["situation"], p["question"], p["options"]])
assert others and not any(x in shown for x in others), (others, p)
assert 2 <= len(p["options"]) <= 4 and p["options"][0].get("recommended") and p["options"][-1]["label"] == "Something else", p["options"]
assert any(s.startswith("Why it is weak:") for s in p["situation"]), p["situation"]
print(f"close asks about {p['claim']} only; {len(others)} other open claims wait")
PY

step "review: a scripted 'run through' runs close, trim, ready --report and explain, and edits no PR"
python3 - "$FIX/ready/close-answers.json" "$WORK/through.json" <<'PY'
import json, sys
json.dump({"go": "run through", "ci": "approve", "close": json.load(open(sys.argv[1]))}, open(sys.argv[2], "w"))
PY
(cd "$CL" && "$U" review 1 --verbose --answers "$WORK/through.json") > "$O/through.txt" 2>&1 || { tail -40 "$O/through.txt"; fail "the run through failed"; }
for s in "== review: close --answers" "== review: trim" "== review: ready --report" "== review: explain" \
         "C03: V11 goes green, and red on control K09" "### Ready checklist" "understando never edits the PR" "review: every step is done."; do
  has "$O/through.txt" "$s"
done
lacks "$O/through.txt" "STOP:"
python3 - "$R/review.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["done"] == ["map", "probe", "formal", "close", "trim", "ready", "explain"], d["done"]
PY
python3 - "$R/trim.json" <<'PY'
import json, sys
t = json.load(open(sys.argv[1]))
assert any(p["path"] == "bin/report.py" for p in t["gate2"]["protected"]), t["gate2"]
assert "wallet/private" not in json.dumps(t), "trim read a secret path"
print("trim keeps the protected path and never reads the secret path")
PY
if grep -rl "$CANARY" "$R" > "$O/canary.txt"; then cat "$O/canary.txt"; fail "a run file holds the secret canary"; fi
git -C "$WT" log --oneline "$AHEAD..HEAD" > "$O/ready-log.txt"; has "$O/ready-log.txt" "understando close"
test "$(git -C "$RV/wallet.git" rev-parse refs/heads/understando/1-ready)" = "$AHEAD" || fail "understando pushed to origin"
test "$(git -C "$RV/wallet.git" rev-parse refs/heads/main)" = "$PR_HEAD" || fail "the PR head moved"
if grep -v '^pr view ' "$RV/gh.log"; then fail "review called gh for more than pr view"; fi
echo "gh calls: $(sort -u "$RV/gh.log" | tr '\n' ';')"

step "doctor: a committed vectors file with no committed generator"
"$U" --run "$R" --repo "$CL" --json doctor > "$O/doctor-review.json"
python3 - "$O/doctor-review.json" <<'PY'
import json, sys
ids = [f["id"] for f in json.load(open(sys.argv[1]))["findings"]]
assert "vectors-no-generator-fee_vectors.jsonl" in ids, ids
assert "ci-unapproved" not in ids, ids
print("doctor flags formal/fee_vectors.jsonl: no committed generator writes it")
PY

step "close refuses an edit on a protected path"
python3 - "$WORK/protected.json" <<'PY'
import json, sys
json.dump({"answers": [{"claim": "C05", "choice": "e2e", "files": {"bin/check_denial.py": "print(1)\n"},
  "verifier": {"description": "A denial check.", "command": {"argv": ["python3", "-m", "unittest", "-q", "bin.check_denial"], "timeout_s": 60}},
  "control": {"description": "Break it.", "edits": [{"op": "replace", "path": "bin/check_denial.py", "find": "1", "replace": "2"}],
              "expect": {"status": "red"}}}]}, open(sys.argv[1], "w"))
PY
"$U" --run "$R" --repo "$CL" close --answers "$WORK/protected.json" > "$O/close-protected.txt"
has "$O/close-protected.txt" "refuse: bin/check_denial.py is protected (owner Ops team"
git -C "$WT" show HEAD:bin/check_denial.py > /dev/null 2>&1 && fail "close wrote a protected file"

step "review: the explainer opens first, at the merge verdict; open --no-open prints the path and the anchor"
cat > "$RV/bin/fake-open" <<OPEN
#!/usr/bin/env bash
echo "\$*" >> "$RV/open.log"
OPEN
chmod +x "$RV/bin/fake-open"
export UNDERSTANDO_OPENER="$RV/bin/fake-open"
"$U" --run "$R" --repo "$CL" explain --html > "$O/explain-html.txt" 2>&1 || { tail -20 "$O/explain-html.txt"; fail "explain --html failed"; }
test -s "$R/explainer.html" || fail "explain --html wrote no page"
"$U" --run "$R" open --anchor C03 --no-open > "$O/open1.txt"
has "$O/open1.txt" "runs/wallet/1/explainer.html"
has "$O/open1.txt" "explainer.html#claim-c03"
"$U" --run "$R" open --level changed --no-open > "$O/open2.txt"; has "$O/open2.txt" "explainer.html#changed"
test ! -f "$RV/open.log" || fail "open --no-open ran the opener"

step "review: a new PR commit and a fix with a new test on -ready: the merge question comes first"
printf '\n[llm]\nkey_source = "env-file"\nenv_file = "%s"\nenv_var = "FAKE_KEY"\nrequire_key_for = ["test_messages"]\n' "$WORK/fake-key.env" >> "$UNDERSTANDO_RUNS/wallet/understando.toml"
printf 'FAKE_KEY=\n' > "$WORK/fake-key.env"
FIXER="$RV/fixer"; git clone -q -b understando/1-ready "$RV/wallet.git" "$FIXER"
cat > "$FIXER/wallet/fees.py" <<'PYF'
"""Added by the PR. No test names this module, and the PR text does not mention it."""


def fee(amount: int) -> int:
    if amount < 0:
        raise ValueError("the amount is below zero")
    return amount // 100 + 1
PYF
cat > "$FIXER/tests/test_fee_floor.py" <<'PYF'
"""A fee for an amount below zero is refused."""

import unittest

from wallet.fees import fee


class FeeFloorTest(unittest.TestCase):
    def test_fee_refuses_an_amount_below_zero(self) -> None:
        with self.assertRaises(ValueError):
            fee(-1)


if __name__ == "__main__":
    unittest.main()
PYF
rg -C "$FIXER" add -A && rg -C "$FIXER" commit -q -m "fix(fees): refuse an amount below zero, with its test"
rg -C "$FIXER" push -q origin HEAD:understando/1-ready
READY_PUSHED="$(git -C "$FIXER" rev-parse HEAD)"
PRW="$RV/author"; git clone -q "$RV/wallet.git" "$PRW"
printf '\n# a later PR commit\n' >> "$PRW/wallet/messages.py"
rg -C "$PRW" commit -q -am "docs(messages): a note from the author"
rg -C "$PRW" push -q origin HEAD:main
PR_HEAD2="$(git -C "$PRW" rev-parse HEAD)"; echo "$PR_HEAD2" > "$RV/head"
(cd "$CL" && "$U" review 1 --json --no-rebuild) > "$O/merge-q.json"
(cd "$CL" && "$U" review 1 --no-rebuild) > "$O/merge-q.txt"
python3 - "$O/merge-q.json" "$ROOT" "$R" <<'PY'
import json, re, sys
sys.path.insert(0, sys.argv[2] + "/scripts")
import prompt as P
d = json.load(open(sys.argv[1]))
p = d["prompt"]
assert p["question"].startswith("Bring the new commit into the review branch? (a merge, no force-push)"), p["question"]
assert p["situation"][0] == "Your PR has 1 new commit that the review branch does not have yet.", p["situation"]
assert [o["label"] for o in p["options"]][0].startswith("Merge, then re-check everything"), p["options"]
assert p["options"][1]["label"].startswith("Show what") and p["options"][2]["label"].startswith("Skip; re-check only"), p["options"]
assert not [x for t in P.user_texts(p) for x in P.plain_problems(t)], p
for line in p["situation"]:
    assert not re.search(r"\b[0-9a-f]{7,40}\b", line) and not re.search(r"\.\w+:\d+", line), line
assert any(l.startswith("I opened the explainer: start with 'Can you merge it?'") for l in p["situation"]), p["situation"]
# The blocker count is the count of the explainer's merge verdict.
n = int(re.search(r"Not ready: (\d+) blockers?", " ".join(p["situation"])).group(1))
page = open(sys.argv[3] + "/explainer.html").read().split('<div id="root">', 1)[1]
story = page[page.index('id="merge"'):page.index('id="story-promises"')]
items = len(re.findall(r"<li><a href=", story.split("data-merge-items", 1)[1].split("</ol>", 1)[0])) if "data-merge-items" in story else 0
more = re.search(r"And (?:<!-- -->)?(\d+)(?:<!-- -->)? more", story)
assert n == items + (int(more.group(1)) if more else 0), (n, items, more)
print(f"the merge question is first; {n} blockers, the same as the explainer")
PY
has "$RV/open.log" "explainer.html#merge"
test -s "$R/opened.jsonl" || fail "review recorded no open event"
WT_TIP0="$(git -C "$WT" rev-parse HEAD)"
(cd "$CL" && "$U" review 1 --show-new) > "$O/show-new.txt"; has "$O/show-new.txt" "docs(messages): a note from the author"
test "$(git -C "$WT" rev-parse HEAD)" = "$WT_TIP0" || fail "--show-new changed the review branch"

step "review: the merge path merges the PR head with a merge commit, no rebase and no push"
(cd "$CL" && "$U" review 1 --merge --no-rebuild) > "$O/merge.txt" 2>&1 || { cat "$O/merge.txt"; fail "the merge failed"; }
has "$O/merge.txt" "Merged the new PR commits into the review branch"
TIP2="$(git -C "$WT" rev-parse HEAD)"
test "$(git -C "$WT" rev-list --parents -n 1 HEAD | wc -w | tr -d ' ')" = 3 || fail "the merge is not a merge commit"
test "$(git -C "$WT" rev-parse HEAD^1)" = "$WT_TIP0" || fail "the first parent is not the old review-branch tip"
git -C "$WT" merge-base --is-ancestor "$PR_HEAD2" HEAD || fail "the PR head is not in the review branch"
git -C "$WT" merge-base --is-ancestor "$READY_PUSHED" HEAD || fail "the review branch lost a commit: a rebase"
test "$(git -C "$RV/wallet.git" rev-parse refs/heads/understando/1-ready)" = "$READY_PUSHED" || fail "understando pushed the merge"

step "review: the new test on -ready is proposed for its claim, one question; then a manual probe counts as the probe step"
(cd "$CL" && "$U" review 1 --json --no-rebuild) > "$O/link-q.json"
python3 - "$O/link-q.json" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))["prompt"]
assert p["question"].startswith("Link the new test to '"), p["question"]
assert "fee floor" in p["situation"][-1] or "fee refuses" in p["situation"][-1] or "test that" in p["situation"][-1], p["situation"]
print(p["question"])
PY
(cd "$CL" && "$U" review 1 --link yes --no-rebuild) > "$O/link.txt"; has "$O/link.txt" "Linked the new test to '"
NEWV="$(python3 -c 'import json,sys; print(next(v["id"] for v in json.load(open(sys.argv[1]))["verifiers"] if v.get("link")))' "$R/trust-map.json")"
python3 - "$R/trust-map.json" "$NEWV" <<'PY'
import json, sys
d, vid = json.load(open(sys.argv[1])), sys.argv[2]
v = next(v for v in d["verifiers"] if v["id"] == vid)
assert v["claims"] == ["C03"] and v["command"]["argv"][-1] == "tests.test_fee_floor.FeeFloorTest", v
k = next(k for k in d["controls"] if k["verifier"] == vid)
assert k["edits"][0]["op"] == "restore-file" and k["edits"][0]["path"] == "wallet/fees.py", k
v["command"]["env_file"] = True     # regression: a verifier with env_file and no key runs with no env file
json.dump(d, open(sys.argv[1], "w"), indent=2)
print(f"{vid} links the new test to C03, with a restore-file control")
PY
"$U" --run "$R" --repo "$CL" probe --only "$NEWV" > "$O/probe-new.txt" 2>&1 || { tail -20 "$O/probe-new.txt"; fail "probe of the new test failed"; }
lacks "$O/probe-new.txt" "needs --env-file"
lacks "$O/probe-new.txt" "skip V07"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); v=next(v for v in d["verifiers"] if v["id"]==sys.argv[2]); assert v["state"]=="proven", v["state"]' "$R/trust-map.json" "$NEWV" \
  || fail "the new test did not go red on the code before the fix"

step "review: --step runs the check stop, then offers the teach stop; teach opens the story first"
(cd "$CL" && "$U" review 1 --go --step --no-rebuild) > "$O/step.txt" 2>&1 || { tail -30 "$O/step.txt"; fail "the step run failed"; }
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["done"]=[x for x in d["done"] if x!="probe"]; json.dump(d, open(sys.argv[1],"w"))' "$R/review.json"
(cd "$CL" && "$U" review 1 --go --step --no-rebuild) > "$O/step2.txt" 2>&1 || { tail -30 "$O/step2.txt"; fail "the second step run failed"; }
has "$O/step2.txt" "already ran at its commit after this review started; done"
has "$O/step2.txt" "Walk through the change before the next stop?"
has "$O/step2.txt" "Walk me through the change"
python3 -c 'import json,sys; t=json.load(open(sys.argv[1]))["timings"]; assert "formal" in t, t' "$R/review.json" || fail "the chain did not reach the formal step"
: > "$RV/open.log"
(cd "$CL" && "$U" review 1 --teach) > "$O/teach1.txt"
python3 - "$O/teach1.txt" "$ROOT" <<'PY'
import re, sys
sys.path.insert(0, sys.argv[2] + "/scripts")
import prompt as P
text = open(sys.argv[1]).read()
lines = text.splitlines()
assert lines[0].startswith("I opened the story"), lines[0]
concepts = [l for l in lines if re.match(r"  \d\. ", l)]
assert 1 <= len(concepts) <= 4, concepts
assert all("(ref: " in l for l in concepts) and "understando snippet " in text, concepts
assert not [x for l in lines for x in P.plain_problems(l)], lines
assert lines[-1].endswith("?") or "next" in lines[-1], lines[-1]
print(f"teach turn 1 opens the story and names {len(concepts)} ideas, each with refs")
PY
has "$RV/open.log" "explainer.html#story"

step "review: a stale explainer is flagged; the first stop rebuilds it"
sleep 1; python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["title"]=(d.get("title") or "")+" (edited)"; json.dump(d, open(sys.argv[1],"w"), indent=2)' "$R/trust-map.json"
(cd "$CL" && "$U" review 1 --json --no-rebuild) > "$O/stale.json"
python3 -c 'import json,sys; s=json.load(open(sys.argv[1]))["prompt"]["situation"]; assert any("out of date" in x for x in s), s' "$O/stale.json" || fail "the stale explainer is not flagged"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["opened"]=None; json.dump(d, open(sys.argv[1],"w"))' "$R/review.json"
(cd "$CL" && "$U" review 1) > "$O/rebuild.txt" 2>&1
has "$O/rebuild.txt" "I rebuilt it ✓"

step "review: run through by default, with one plain progress line for each item; --json gives NDJSON events"
(cd "$CL" && "$U" review 1 --go --json) > "$O/through2.ndjson" 2> "$O/through2.err" || { tail -30 "$O/through2.err"; fail "the run through failed"; }
python3 - "$O/through2.ndjson" "$ROOT" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[2] + "/scripts")
import prompt as P
text = open(sys.argv[1]).read()
events = [json.loads(l) for l in text.splitlines() if l.startswith('{"event"')]
assert events and all(e["id"] and e["text"][-1] in "✓✗" or "✗" in e["text"] for e in events), events
for e in events:
    assert not P.plain_problems(e["text"]), e
final = json.loads(text[text.index("\n{\n") + 1:] if "\n{\n" in text else text[text.index("{\n"):])
assert "done" in final or "prompt" in final, list(final)
print(f"{len(events)} progress events; the last object has {sorted(final)[:4]}")
PY

step "review: a failed step is recorded; the next run asks to retry or skip it; --json always prints JSON"
cp "$R/trust-map.json" "$WORK/map-good.json"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["claims"][0]["bogus"]=1; json.dump(d, open(sys.argv[1],"w"))' "$R/trust-map.json"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["done"]=[]; json.dump(d, open(sys.argv[1],"w"))' "$R/review.json"
(cd "$CL" && "$U" review 1 --go --no-rebuild) > "$O/fail1.txt" 2>&1 && fail "review --go passed with an invalid map"
has "$O/fail1.txt" "Map ✗"
(cd "$CL" && "$U" review 1 --json --no-rebuild) > "$O/fail2.json"
python3 -c 'import json,sys; p=json.load(open(sys.argv[1]))["prompt"]; assert p["question"]=="Retry the map step?" and p["options"][1]["label"]=="Skip map", p' "$O/fail2.json" \
  || fail "no retry-or-skip question after a failed step"
cp "$WORK/map-good.json" "$R/trust-map.json"
(cd "$WORK" && "$U" review 1 --json) > "$O/err.json" 2>/dev/null || true
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["error"], d' "$O/err.json" || fail "review --json printed no JSON error"

step "map: a run folder with no history diffs against the map as it was"
R3="$WORK/run-nohist"; cp -R "$R" "$R3"; rm -rf "$R3/history"
"$U" --run "$R3" --repo "$CL" map > "$O/map-nohist.txt"
lacks "$O/map-nohist.txt" "first one"
has "$O/map-nohist.txt" "# Trust-map diff"
unset UNDERSTANDO_RUNS

step "signals: a possible bug whose code changed on -ready asks for a re-check, not discover"
RB="$WORK/run-bug"; cp -R "$RUN" "$RB"
RBR="$WORK/bug-repo"; git clone -q --single-branch --branch main "$REPO" "$RBR"
BUG="$(python3 -c 'import json,sys; print(next(i["id"] for i in json.load(open(sys.argv[1]))["invariants"] if i.get("possible_bug")))' "$RB/trust-map.json")"
BUGLOC="$(python3 -c 'import json,re,sys; i=next(i for i in json.load(open(sys.argv[1]))["invariants"] if i.get("possible_bug")); print(next(e for e in i["evidence"] if re.match(r"[\w/]+\.py:\d", e)))' "$RB/trust-map.json")"
BUGFILE="${BUGLOC%%:*}"; BUGLINE="${BUGLOC#*:}"; BUGLINE="${BUGLINE%%[-,]*}"
rg -C "$RBR" checkout -q -b understando/1-ready
printf '\n# a note far from the bug\n' >> "$RBR/wallet/messages.py"
rg -C "$RBR" commit -q -am "-ready: a note in messages.py"
"$U" --run "$RB" --repo "$RBR" --json menu --pr-head "$HEAD" > "$O/bug1.json"
python3 - "$O/bug1.json" "$BUG" <<'PY'
import json, sys
d, bug = json.load(open(sys.argv[1])), sys.argv[2]
p = {x["verb"]: x for x in d["recommend"]}
assert "discover" in p and bug in p["discover"]["why"] and "did not change" in p["discover"]["why"], d["recommend"]
assert not any(x["label"].startswith("re-check " + bug) for x in d["recommend"]), d["recommend"]
print(f"the code of {bug} is unchanged on -ready: {p['discover']['label']}")
PY
sed -i.bak "${BUGLINE}s/\$/  # fixed on -ready/" "$RBR/$BUGFILE" && rm "$RBR/$BUGFILE.bak"
rg -C "$RBR" commit -q -am "-ready: fix the possible bug"
FIXSHA="$(git -C "$RBR" rev-parse --short=7 HEAD)"
"$U" --run "$RB" --repo "$RBR" --json menu --pr-head "$HEAD" > "$O/bug2.json"
"$U" --run "$RB" --repo "$RBR" menu --pr-head "$HEAD" > "$O/bug2.txt"
python3 - "$O/bug2.json" "$BUG" "$BUGFILE" "$FIXSHA" <<'PY'
import json, sys
d, bug, path, sha = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3], sys.argv[4]
first = d["recommend"][0]
assert first["verb"] == "map" and first["label"].startswith("Re-check the fix for '") and bug not in first["label"], d["recommend"]
assert "map + probe on the changed code" in first["why"] and path in first["why"] and sha in first["why"], first["why"]
assert all(bug not in x["why"] for x in d["recommend"] if x["verb"] == "discover"), d["recommend"]
b = d["signals"]["discover"]["bug_changes"][0]
assert b["changed"] and b["claims"], b
print(f"-ready changed {path}: {first['label']}: {first['why'][:110]}")
PY
has "$O/bug2.txt" "1. Re-check the fix for '"

step "ci: the approval is one question with a project option, and --project approves only that project"
CR="$WORK/mono"; mkdir -p "$CR/.github/workflows" "$CR/projects/alpha/tests" "$CR/projects/beta/tests"
printf '[[projects]]\nname = "alpha"\npath = "projects/alpha"\n\n[[projects]]\nname = "beta"\npath = "projects/beta"\n' > "$CR/catalog.toml"
for pj in alpha beta; do
  printf 'name: %s\non:\n  pull_request:\njobs:\n  test-%s:\n    runs-on: ubuntu-latest\n    defaults:\n      run:\n        working-directory: projects/%s\n    steps:\n      - name: Tests\n        run: python3 -m unittest discover -s tests\n' "$pj" "$pj" "$pj" > "$CR/.github/workflows/$pj.yml"
done
printf 'x = 1\n' > "$CR/projects/alpha/a.py"; printf 'y = 1\n' > "$CR/projects/beta/b.py"
git -C "$CR" init -q -b main; rg -C "$CR" add -A; rg -C "$CR" commit -q -m base
MBASE="$(git -C "$CR" rev-parse HEAD)"
printf 'x = 2\n' > "$CR/projects/alpha/a.py"; printf 'z = 1\n' > "$CR/projects/alpha/c.py"; printf 'y = 2\n' > "$CR/projects/beta/b.py"
printf '# a root change\n' >> "$CR/.github/workflows/alpha.yml"
rg -C "$CR" add -A; rg -C "$CR" commit -q -m "the PR"
MHEAD="$(git -C "$CR" rev-parse HEAD)"
MR="$WORK/mono-run"; mkdir -p "$MR"
"$U" --run "$MR" --repo "$CR" --pr 7 ci --head "$MHEAD" --base "$MBASE" > /dev/null
"$U" --run "$MR" --repo "$CR" --pr 7 --json ci --head "$MHEAD" --base "$MBASE" --question > "$O/ci-q.json"
"$U" --run "$MR" --repo "$CR" --pr 7 ci --head "$MHEAD" --base "$MBASE" --question > "$O/ci-q.txt"
python3 - "$O/ci-q.json" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))["prompt"]
labels = [o["label"] for o in p["options"]]
assert labels == ["Approve all 2", "Show the list", "Approve only alpha", "Something else"], labels
assert p["options"][0]["recommended"] and p["options"][2]["run"] == "understando ci --approve --project alpha", p["options"]
assert "workflow files" in p["situation"][0] and "every project" in p["situation"][0], p["situation"]
print(p["situation"][0])
PY
has "$O/ci-q.txt" "3. Approve only alpha:"
"$U" --run "$MR" --repo "$CR" --pr 7 ci --approve --project alpha > "$O/ci-proj.txt"
has "$O/ci-proj.txt" "approved 1 command of alpha"
"$U" --run "$MR" ci --check-argv python3 -m unittest discover -s tests > "$O/ci-check.txt" || true
python3 - "$MR/ci.json" "$ROOT" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[2] + "/scripts")
import ci
prof = json.load(open(sys.argv[1]))
ok = ci.approved_commands(prof)
assert [c["project"] for c in ok] == ["alpha"], ok
assert ci.approved(prof) and not ci.fully_approved(prof)
beta = next(c for c in prof["commands"] if c["project"] == "beta")
alpha = next(c for c in prof["commands"] if c["project"] == "alpha")
assert ci.allowed_by({"commands": ok}, beta["argv"], beta["cwd"]) is None, "a beta command passes the alpha-only approval"
assert ci.allowed_by({"commands": ok}, alpha["argv"], alpha["cwd"]), "the alpha command is refused"
print("--project alpha approves only the alpha command; the beta command stays refused")
PY

step "mode off: the hook writes nothing"
"$U" mode off > /dev/null
N="$(wc -l < "$RUN/journal.jsonl")"
echo '{"prompt": "This prompt must not be noted."}' | "$U" hook user-prompt
test "$(wc -l < "$RUN/journal.jsonl")" = "$N" || fail "the hook wrote while the mode was off"
test "$(git -C "$REPO" rev-parse main)" = "$HEAD" || fail "the PR's own commits changed"
step "probe: an e2e verifier that only calls internal functions is flagged and becomes integration"
RUP="$WORK/run-userpath"; cp -R "$RUN" "$RUP"
python3 - "$RUP/trust-map.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
d["verifiers"].append({"id": "V99", "kind": "e2e", "claims": ["C02"], "tier": "fact",
    "description": "BalanceTest is labelled end to end, but it calls withdraw directly.",
    "command": {"argv": ["python3", "-m", "unittest", "-q", "tests.test_core.BalanceTest"], "timeout_s": 60},
    "independence": {"by": "tool", "tool": "unittest"}, "cost": {"usd": 0}, "provenance": "the e2e test"})
json.dump(d, open(sys.argv[1], "w"), indent=2)
PY
E2EV="$(python3 -c 'import json,sys; print(next(v["id"] for v in json.load(open(sys.argv[1]))["verifiers"] if v["kind"]=="e2e" and v["id"]!="V99"))' "$RUP/trust-map.json")"
"$U" --run "$RUP" --repo "$REPO" probe --only "V99,$E2EV" > "$O/probe-up.txt" 2>&1 || { tail -20 "$O/probe-up.txt"; fail "probe failed"; }
has "$O/probe-up.txt" "FLAG NOT-USER-PATH: V99 is labelled e2e, but it only calls internal functions: not a user-path e2e."
python3 - "$RUP/trust-map.json" "$E2EV" <<'PY'
import json, sys
d = {v["id"]: v for v in json.load(open(sys.argv[1]))["verifiers"]}
assert d["V99"]["kind"] == "integration" and d["V99"]["user_path"]["result"] == "internal-only" and d["V99"]["user_path"]["claimed_kind"] == "e2e", d["V99"]
assert d[sys.argv[2]]["kind"] == "e2e" and d[sys.argv[2]]["user_path"]["result"] == "user-path", d[sys.argv[2]]
print(f"V99 is integration (not a user-path e2e); {sys.argv[2]} drives a process, so it stays e2e")
PY

step "entry points: help shows review, open and build; the rest is advanced; a bare menu recommends build, open or review"
"$U" help > "$O/help.txt"
for v in review open build; do grep -qE "^  $v " "$O/help.txt" || fail "help lacks $v"; done
has "$O/help.txt" "Advanced verbs: \`understando help --all\`."
if grep -qE "^  discover " "$O/help.txt"; then fail "help shows an advanced verb"; fi
"$U" help --all > "$O/help-all.txt"; has "$O/help-all.txt" "  discover"
python3 -c 'import json,sys; t={v["id"]: v["tier"] for v in json.load(open(sys.argv[1]))["verbs"]}; assert {k for k,v in t.items() if v=="entry"} == {"review","open","build"}, t' "$ROOT/commands.json"
(cd "$WORK" && "$U" --json menu) > "$O/menu-build.json"
python3 -c 'import json,sys; p=json.load(open(sys.argv[1]))["recommend"]; assert p[0]["verb"]=="build", p' "$O/menu-build.json" || fail "the bare menu does not recommend build"
git -C "$CL" update-ref refs/remotes/origin/understando/7-review HEAD
(cd "$CL" && "$U" --json menu) > "$O/menu-open.json"
python3 -c 'import json,sys; p=json.load(open(sys.argv[1]))["recommend"]; assert p[0]["command"]=="understando open 7", p' "$O/menu-open.json" || fail "the menu does not recommend open on a review branch"
if (cd "$CL" && UNDERSTANDO_RUNS="$WORK/runs" "$U" open 7 --no-open) > "$O/open7.txt"; then fail "open 7 passed with no run and no fetch helper"; fi
has "$O/open7.txt" "fetch_review_branch"

step "open: the reviewer path asks one question; a question is a confusion row at its anchor, in the local journal only"
(cd "$CL" && UNDERSTANDO_RUNS="$WORK/runs" "$U" open 1 --no-open) > "$O/open-r.txt"
has "$O/open-r.txt" "How do you want to read it?"
has "$O/open-r.txt" "1. Walk me through it (recommended)"
(cd "$CL" && UNDERSTANDO_RUNS="$WORK/runs" "$U" open 1 --teach --no-open) > "$O/open-teach.txt"
has "$O/open-teach.txt" "the story"
(cd "$CL" && UNDERSTANDO_RUNS="$WORK/runs" "$U" open 1 --ask "I do not get the restore step." --anchor C03 --no-open) > "$O/open-ask.txt"
has "$O/open-ask.txt" "nothing is pushed"
python3 -c 'import json,sys; r=[json.loads(l) for l in open(sys.argv[1])][-1]; assert r["kind"]=="confusion" and r["anchor"]=="claim-c03", r' "$WORK/runs/wallet/1/journal.jsonl" \
  || fail "no confusion row with its anchor"
step "review offline: gh exits 1 and the remote is unreachable; the last known head, offline mode, the merge question skipped"
NO="$WORK/offline"; mkdir -p "$NO/bin" "$NO/runs"
printf '#!/usr/bin/env bash\necho "Error connecting to api.github.com" >&2; exit 1\n' > "$NO/bin/gh"; chmod +x "$NO/bin/gh"
cp -R "$WORK/runs/wallet" "$NO/runs/wallet"
git clone -q "$RV/wallet.git" "$NO/clone"; CL2="$NO/clone"
git -C "$CL2" remote set-url origin "$NO/gone/wallet.git"
# The newer commit sits on the last known head of the run (an earlier step moved it past PR_HEAD).
LASTH="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["head"])' "$NO/runs/wallet/1/review.json")"
NEWC="$(git -C "$CL2" -c user.name=f -c user.email=f@example.invalid commit-tree -p "$LASTH" -m "a newer PR commit" "$LASTH^{tree}")"
git -C "$CL2" update-ref refs/remotes/origin/feature "$NEWC"
python3 - "$NO/runs/wallet/1/review.json" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); d["head_branch"] = "feature"; d.pop("merge", None); json.dump(d, open(p, "w"))
PY
(cd "$CL2" && PATH="$NO/bin:$PATH" UNDERSTANDO_RUNS="$NO/runs" "$U" review 1 --json) > "$O/review-offline.json" || { cat "$O/review-offline.json"; fail "offline review stopped"; }
python3 - "$O/review-offline.json" "$NO/runs/wallet/1/review.json" "$NEWC" <<'PY'
import json, sys
d, st, newc = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), sys.argv[3]
assert d["offline"] is True and d["offline_reason"], d.get("offline_reason")
assert d["prompt"]["situation"][0].startswith("I can't reach GitHub, so I can't see new PR commits. I'm using the last known PR head (from "), d["prompt"]["situation"]
assert d["head"] == newc, d["head"]
assert "Bring" not in d["prompt"]["question"], d["prompt"]["question"]
assert st["merge"]["decision"] == "skipped" and st["merge"]["offline"] is True, st.get("merge")
assert st["offline"] is True
PY
(cd "$CL2" && PATH="$NO/bin:$PATH" UNDERSTANDO_RUNS="$NO/runs" "$U" review 1 --go --no-open) > "$O/review-offline-go.txt" || true
has "$O/review-offline-go.txt" "map"
(cd "$CL2" && PATH="$NO/bin:$PATH" UNDERSTANDO_RUNS="$NO/runs" "$U" publish 1 --dry-run) > "$O/publish-offline.txt" && fail "publish ran offline"
has "$O/publish-offline.txt" "I can't reach GitHub"

step "review: gh fails but git ls-remote works (a local file remote); the head is resolved from refs/pull/N/head"
git -C "$RV/wallet.git" update-ref refs/pull/9/head "$PR_HEAD"
LR="$WORK/lsr"; mkdir -p "$LR/runs"; cp "$WORK/runs/wallet/understando.toml" "$LR/runs/"; mkdir -p "$LR/runs/wallet"; mv "$LR/runs/understando.toml" "$LR/runs/wallet/"
git clone -q "$RV/wallet.git" "$LR/clone"
(cd "$LR/clone" && PATH="$NO/bin:$PATH" UNDERSTANDO_RUNS="$LR/runs" "$U" review 9 --json) > "$O/review-lsr.json" || { cat "$O/review-lsr.json"; fail "review with ls-remote stopped"; }
python3 - "$O/review-lsr.json" "$PR_HEAD" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["head"] == sys.argv[2] and d["offline"] is False, (d["head"], d["offline"])
PY

step "review: no run and no network gives the plain error"
NR="$WORK/norun"; mkdir -p "$NR/runs"; git clone -q "$RV/wallet.git" "$NR/clone"; git -C "$NR/clone" remote set-url origin "$NO/gone/wallet.git"
if (cd "$NR/clone" && PATH="$NO/bin:$PATH" UNDERSTANDO_RUNS="$NR/runs" "$U" review 4 --json) > "$O/review-norun.txt" 2>&1; then fail "review passed with no head"; fi
has "$O/review-norun.txt" "I can't reach GitHub and there is no earlier review of PR 4. Run this where the network is available, or pass --head <sha>."

step "tool probes: a hung npx never stops review or doctor, the result is cached, and refusal rules are in the router"
TP="$WORK/toolprobe"; mkdir -p "$TP/bin" "$TP/uhome" "$TP/npm"
printf '#!/bin/sh\necho called >> "%s/npx-calls"\nsleep 30\n' "$TP" > "$TP/bin/npx"; chmod +x "$TP/bin/npx"
t0=$(date +%s)
env -u UNDERSTANDO_OFFLINE PATH="$TP/bin:$PATH" UNDERSTANDO_HOME="$TP/uhome" npm_config_cache="$TP/npm" HOME="$TP/npm" \
  "$U" --run "$RUN" --json doctor > "$O/doctor-hung.json"
env -u UNDERSTANDO_OFFLINE PATH="$TP/bin:$PATH" UNDERSTANDO_HOME="$TP/uhome" npm_config_cache="$TP/npm" HOME="$TP/npm" \
  "$U" --run "$RUN" signals > "$O/signals-hung.json"
[ $(( $(date +%s) - t0 )) -lt 25 ] || fail "a hung npx held doctor and signals for 25 s or more"
python3 - "$O/doctor-hung.json" <<'PY'
import json, sys
f = [x for x in json.load(open(sys.argv[1]))["findings"] if x["id"] == "toolchain-cc-check"]
assert f and f[0]["severity"] == "mention" and "not checked (timed out)" in f[0]["summary"], f
PY
test ! -e "$TP/uhome/toolprobe.json" || python3 -c 'import json,sys; assert "cc-check" not in json.load(open(sys.argv[1]))' "$TP/uhome/toolprobe.json" \
  || fail "a timed-out probe was cached"
rm -f "$TP/npx-calls"
python3 - "$TP/uhome/toolprobe.json" <<'PY'
import json, sys, time
json.dump({"cc-check": {"value": "npx @spolu/cc-check@0.2.0", "at": time.time()}}, open(sys.argv[1], "w"))
PY
env -u UNDERSTANDO_OFFLINE PATH="$TP/bin:$PATH" UNDERSTANDO_HOME="$TP/uhome" npm_config_cache="$TP/npm" HOME="$TP/npm" \
  "$U" --run "$RUN" signals > "$O/signals-cached.json"
python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["toolchains"]["cc-check"], "cache not used"' "$O/signals-cached.json"
test ! -e "$TP/npx-calls" || fail "a cached probe result still called npx"
has "$ROOT/SKILL.md" "refuses a step that the task needs, stop and report the refusal word for word"
has "$ROOT/SKILL.md" "only a diagnostic"
has "$ROOT/SKILL.md" "Never retry a refused command another way."
has "$ROOT/references/working-rules.md" "Do not poll processes."
echo "tool probes: timeout is a mention, the cache is reused, the router has the new rules"

echo "PASS: mode e2e"
