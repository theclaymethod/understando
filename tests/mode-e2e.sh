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
assert c["C01"]["verdict"] == "Formal" and c["C01"]["tier"] == 5, c["C01"]
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
has "$O/review3.txt" "STOP: the CI profile is not approved"
if "$U" --run "$R" --repo "$CL" probe > "$O/probe-noci.txt"; then fail "probe ran with an unapproved CI profile"; fi
has "$O/probe-noci.txt" "refuse: the CI profile is not approved"

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

step "review: a scripted 'run through' runs map, probe, close, trim, ready --report and explain, and edits no PR"
python3 - "$FIX/ready/close-answers.json" "$WORK/through.json" <<'PY'
import json, sys
json.dump({"go": "run through", "ci": "approve", "close": json.load(open(sys.argv[1]))}, open(sys.argv[2], "w"))
PY
(cd "$CL" && "$U" review 1 --answers "$WORK/through.json") > "$O/through.txt" 2>&1 || { tail -40 "$O/through.txt"; fail "the run through failed"; }
for s in "== review: map" "== review: probe" "== review: close --answers" "== review: trim" "== review: ready --report" "== review: explain" \
         "C03: V09 goes green, and red on control K09" "### Ready checklist" "understando never edits the PR" "review: every step is done."; do
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
unset UNDERSTANDO_RUNS

step "mode off: the hook writes nothing"
"$U" mode off > /dev/null
N="$(wc -l < "$RUN/journal.jsonl")"
echo '{"prompt": "This prompt must not be noted."}' | "$U" hook user-prompt
test "$(wc -l < "$RUN/journal.jsonl")" = "$N" || fail "the hook wrote while the mode was off"
test "$(git -C "$REPO" rev-parse main)" = "$HEAD" || fail "the PR's own commits changed"
echo "PASS: mode e2e"
