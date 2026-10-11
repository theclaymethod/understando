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
O="$WORK/out"; mkdir -p "$O"

step "setup: the skill links and the CLI link, in the fake HOME"
bash "$ROOT/scripts/setup.sh" --links-only > "$O/setup.txt"
for d in .agents .claude .codex .cursor; do
  test "$(readlink "$FH/$d/skills/understando")" = "$ROOT" || fail "no link $FH/$d/skills/understando"
done
test "$(readlink "$FH/.local/bin/understando")" = "$ROOT/bin/understando" || fail "no CLI link"
for d in .agents .claude .codex .cursor; do
  l="$REAL_HOME/$d/skills/understando"
  if [ -L "$l" ] && [ "$(readlink -f "$l")" != "$(readlink -f "$ROOT")" ]; then fail "$l points to another skill"; fi
  [ -e "$l" ] && echo "real link ok: $l" || echo "real link absent: $l (run setup)"
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

step "mode: off, then on, then status"
"$U" mode status > "$O/mode0.txt"; has "$O/mode0.txt" "understando mode: off"
"$U" --run "$RUN" --repo "$REPO" --pr 1 mode on > "$O/mode1.txt"; has "$O/mode1.txt" "understando mode: on"
"$U" --json mode status > "$O/mode2.json"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["on"] and d["run"].endswith("/run") and str(d["pr"]) == "1", d' "$O/mode2.json"

step "bare menu: two or three verbs from signals, then the table"
"$U" > "$O/menu.txt"
has "$O/menu.txt" "recommended next"; has "$O/menu.txt" "Get ready"; has "$O/menu.txt" "Nothing runs until you choose one."
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
     "examples": [{"question": "What should withdraw do when amount is below zero?", "expr": "withdraw(10, -5)", "raises": "ValueError"}]},
    {"candidate": find("The wallet module is safe"), "decision": "accept"}],
  "rest": {"decision": "defer", "reason": "Not in scope for this review."}}, open(sys.argv[2], "w"))
PY
"$U" discover answer --answers "$WORK/discover-answers.json" > "$O/discover1.txt"
has "$O/discover1.txt" "reword as I02 (accepted, author user"
has "$O/discover1.txt" "reject: The message text is copy, not a rule."
has "$O/discover1.txt" "POSSIBLE BUG"
has "$O/discover1.txt" "the code gives 15"
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

step "close: an e2e test closes the Gap, a property test closes an Asserted claim, one waiver"
"$U" close --list > "$O/queue.txt"
test "$(head -1 "$O/queue.txt" | cut -d' ' -f1-2)" = "C03 Gap:" || fail "the riskiest claim is not first"
"$U" close --answers "$FIX/ready/close-answers.json" > "$O/close.txt"
has "$O/close.txt" "C03: V09 goes green, and red on control K09"
has "$O/close.txt" "C02: V10 goes green, and red on control K10"
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

step "ready --report: the four gates"
"$U" ready --report > "$O/ready.txt"
for g in "gate 1 verified: pass" "gate 2 no excess code: fail" "gate 3 no unit test that an e2e test covers: pass" "gate 4 explainable: pass" "Independent review"; do
  has "$O/ready.txt" "$g"
done

step "explain: the why level from the journal, the checklist on top, the glossary file"
"$U" explain > "$O/explain.txt"
WHY="$RUN/chapters/01a-why.mdx"
test -f "$WHY" || fail "no why level"
has "$WHY" "Make sure the fee is right for each amount"
has "$WHY" '#claim-c03'
has "$WHY" "Confirmed by the user: The fee is one"
has "$WHY" "Proposed, not confirmed"
has "$RUN/explainer.mdx" "Why it was built this way"
has "$RUN/pr-section.md" "### Ready checklist"
has "$RUN/pr-section.md" "**Formal**"
has "$RUN/pr-section.md" "waived: The wallet keeps no shared state"
has "$RUN/GLOSSARY.md" "**Overdraft**:"
python3 - "$WHY" "$WORK/why-prose.md" <<'PY'
# The STE lint covers the generated prose of the why level, not the user's quotes.
import json, re, sys
text = open(sys.argv[1]).read()
text = re.sub(r'<blockquote data-quote="user">.*?</blockquote>', "", text, flags=re.S)
out = []
for m in re.finditer(r'\{(".*?(?<!\\)")\}', text):
    s = json.loads(m.group(1))
    if len(s.split()) > 3 and not re.match(r"[A-Z]\d\d: ", s):
        out.append(s)
open(sys.argv[2], "w").write("\n\n".join(out) + "\n")
PY
LINT="$(find "$FH/.agents/skills/asd-ste100/" -name ste-lint.py | head -1)"
python3 -I "$LINT" "$WORK/why-prose.md" | tee "$O/lint.txt" | tail -1
grep -q "(0 hard" "$O/lint.txt" || fail "the why level prose has hard STE violations"

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

step "mode off: the hook writes nothing"
"$U" mode off > /dev/null
N="$(wc -l < "$RUN/journal.jsonl")"
echo '{"prompt": "This prompt must not be noted."}' | "$U" hook user-prompt
test "$(wc -l < "$RUN/journal.jsonl")" = "$N" || fail "the hook wrote while the mode was off"
test "$(git -C "$REPO" rev-parse main)" = "$HEAD" || fail "the PR's own commits changed"
echo "PASS: mode e2e"
