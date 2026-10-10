#!/usr/bin/env bash
# End-to-end test: run understando map, controls, verdicts, rerun and explain on the fixture repo,
# then assert the exact verdicts in tests/fixture/expected.json.
#
#   tests/e2e.sh            KEEP=1 tests/e2e.sh keeps the work dir
#
# The map step here is the deterministic half: tests/fixture/inventory.json stands in for the
# claims and verifiers that an agent reads from tests/fixture/PR.md, and scan.py adds the rest.
# No model call. No network, when the npm cache holds cc-check (scripts/setup.sh puts it there).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIX="$ROOT/tests/fixture"
S="$ROOT/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/understando-e2e.XXXXXX")"
REPO="$WORK/repo"
MAP="$WORK/trust-map.json"
export E2E_TELEMETRY_DISABLED=1 DO_NOT_TRACK=1
cleanup() { if [ "${KEEP:-0}" = 1 ]; then echo "kept $WORK"; else rm -rf "$WORK"; fi; }
trap cleanup EXIT

step() { printf '\n== %s\n' "$*"; }
g() { git -C "$REPO" -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false "$@"; }

step "build the fixture repo: base commit, then the PR commit"
mkdir -p "$REPO"
cp -R "$FIX/base/." "$REPO/"
g init -q -b main
g add -A && g commit -q -m "base"
BASE="$(g rev-parse HEAD)"
cp -R "$FIX/head/." "$REPO/"
g add -A && g commit -q -m "Refuse overdrafts in the wallet"
HEAD="$(g rev-parse HEAD)"
sed -e "s/BASE_SHA/$BASE/" -e "s/HEAD_SHA/$HEAD/" "$FIX/inventory.json" > "$MAP"
BEFORE_STATUS="$(g status --porcelain)"
BEFORE_TREES="$(g worktree list | wc -l | tr -d ' ')"

step "map: scan the PR, add contract claims and Gap candidates, validate"
python3 "$S/scan.py" --repo "$REPO" --base "$BASE" --head "$HEAD" --src-prefix wallet/ --test-prefix tests/ --add "$MAP"
python3 - "$MAP" "$FIX/plain.json" <<'PY'
# The map step writes plain text for each claim. scan.py adds claims without it, so the
# fixture holds the agent's plain text for those claims.
import json, sys
data, plain = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
for claim in data["claims"]:
    if "plain" not in claim and claim["id"] in plain:
        claim["plain"] = plain[claim["id"]]
json.dump(data, open(sys.argv[1], "w"), indent=2)
PY
python3 "$S/validate.py" "$MAP"

step "controls: baseline at the head, then one scratch worktree per control"
python3 "$S/run_control.py" --map "$MAP" --repo "$REPO" --baseline --scratch "$WORK/scratch"
python3 "$S/run_control.py" --map "$MAP" --repo "$REPO" --all --scratch "$WORK/scratch"

step "verdicts"
python3 "$S/verdicts.py" "$MAP"
python3 "$S/verdicts.py" "$MAP" --check
python3 "$S/validate.py" "$MAP"

step "rerun: diff the map against a copy of itself"
cp "$MAP" "$WORK/previous.json"
python3 "$S/rerun.py" "$WORK/previous.json" "$MAP" --fail-on-drop | tee "$WORK/rerun.md"
grep -q "No verdict, state or control result changed." "$WORK/rerun.md"

step "explain: PR-body section, three-level source, HTML"
python3 "$S/explain.py" --map "$MAP" --repo "$REPO" --out "$WORK/explain"
# UNDERSTANDO_VE_RUNTIME pins an Artifacture checkout. explain.py reads it too.
if [ -n "${UNDERSTANDO_VE_RUNTIME:-}" ]; then
  VE="$UNDERSTANDO_VE_RUNTIME"
else
  VE="$(dirname "$(readlink -f "$HOME/.claude/skills/visual-explainer/SKILL.md" 2>/dev/null || echo "$HOME/.claude/skills/visual-explainer/SKILL.md")")"
fi
node "$VE/scripts/artifacture.mjs" export "$WORK/explain/explainer.mdx" --out "$WORK/explain/explainer.html"
test -s "$WORK/explain/explainer.html"
python3 - "$MAP" "$WORK/explain/explainer.html" <<'PY'
import json, sys
claims = json.load(open(sys.argv[1]))["claims"]
html = open(sys.argv[2], encoding="utf-8").read()
missing = [c["id"] for c in claims
           if not c.get("plain") or (c["plain"]["what"] not in html and json.dumps(c["plain"]["what"])[1:-1] not in html)]
if missing:
    sys.exit(f"FAIL: the explainer has no plain.what text for {missing}")
print(f"the explainer shows plain.what for all {len(claims)} claims")
PY
python3 - "$MAP" "$WORK/explain" <<'PY'
# One self-contained MDX unit per chapter, and the guided tour shows each claim at a step.
import json, pathlib, re, sys
claims = json.load(open(sys.argv[1]))["claims"]
chapters = pathlib.Path(sys.argv[2]) / "chapters"
names = ["01-orientation", "02-tour", "03-confidence", "04-evidence", "05-tradeoffs", "06-exercises"]
missing = [n for n in names if not (chapters / f"{n}.mdx").is_file()]
if missing:
    sys.exit(f"FAIL: missing chapter files {missing}")
entry = (pathlib.Path(sys.argv[2]) / "explainer.mdx").read_text()
for n in names:
    text = (chapters / f"{n}.mdx").read_text()
    if "visual-explainer-mdx/components" not in text.split("\n", 2)[1] or f"./chapters/{n}.mdx" not in entry:
        sys.exit(f"FAIL: chapter {n} does not import its components, or the entry does not import it")
tour = (chapters / "02-tour.mdx").read_text()
absent = [c["id"] for c in claims if not re.search(r'"text":\s*"' + c["id"] + '"', tour)]
if absent:
    sys.exit(f"FAIL: the guided tour does not show {absent}")
print(f"{len(names)} chapter units; the guided tour shows all {len(claims)} claims")
PY
LINT="$(find "$HOME/.claude/skills/asd-ste100/scripts" "$HOME/.agents/skills/asd-ste100/scripts" -name ste-lint.py 2>/dev/null | head -1)"
python3 -I "$LINT" "$WORK/explain/pr-section.md" | tail -2

step "assert: exact verdicts, verifier states, loud flags, and a clean repo"
python3 - "$MAP" "$FIX/expected.json" <<'PY'
import json, sys
got, want = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
verdicts = {c["id"]: c["verdict"] for c in got["claims"]}
states = {v["id"]: v["state"] for v in got["verifiers"]}
loud = sorted([f["flag"], f["subject"]] for f in got["flags"] if f.get("loud"))
print(f"{'claim':<6}{'expected':<10}{'actual':<10}text")
for cid in sorted(set(verdicts) | set(want["verdicts"])):
    text = next((c["text"] for c in got["claims"] if c["id"] == cid), "")
    print(f"{cid:<6}{want['verdicts'].get(cid, '-'):<10}{verdicts.get(cid, '-'):<10}{text}")
print("loud flags:", loud)
problems = []
if verdicts != want["verdicts"]: problems.append("verdicts differ")
if states != want["states"]: problems.append(f"states differ: {states}")
if loud != sorted(want["loud_flags"]): problems.append("loud flags differ")
if got["summary"] != want["summary"]: problems.append(f"summary differs: {got['summary']}")
gap = next(c for c in got["claims"] if c["id"] == "C03")
if gap["code"][0]["path"] != "wallet/fees.py": problems.append("the Gap is not wallet/fees.py")
if problems:
    sys.exit("FAIL: " + "; ".join(problems))
print("verdicts match expected.json")
PY
test "$(g status --porcelain)" = "$BEFORE_STATUS" || { echo "FAIL: the fixture checkout changed"; exit 1; }
test "$(g worktree list | wc -l | tr -d ' ')" = "$BEFORE_TREES" || { echo "FAIL: a scratch worktree is left"; exit 1; }
test -z "$(ls -A "$WORK/scratch")" || { echo "FAIL: scratch dir is not empty"; exit 1; }
echo
echo "PASS: understando e2e on the fixture"
