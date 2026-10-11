#!/usr/bin/env bash
# End-to-end test: run understando map, controls, verdicts, rerun and explain on the fixture repo,
# then assert the exact verdicts in tests/fixture/expected.json. Then tests/mode-e2e.sh drives the
# understando CLI: the mode, the menu, discover, close, trim, ready, explain, routes and doctor.
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
python3 - "$MAP" "$FIX/promises.json" <<'PY'
# The map step writes three to six promises after the scan, so each claim, also each added one,
# belongs to exactly one promise.
import json, sys
data = json.load(open(sys.argv[1]))
data["promises"] = json.load(open(sys.argv[2]))
json.dump(data, open(sys.argv[1], "w"), indent=2)
PY
python3 "$S/mechanical.py" --map "$MAP" --repo "$REPO"
python3 "$S/validate.py" "$MAP"

step "validate: a claim in two promises, or in none, fails"
python3 - "$MAP" "$WORK/two-promises.json" "$WORK/no-promise.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
two = json.loads(json.dumps(data)); two["promises"][1]["claims"].append("C01")
none = json.loads(json.dumps(data)); none["promises"][0]["claims"].remove("C02")
json.dump(two, open(sys.argv[2], "w")); json.dump(none, open(sys.argv[3], "w"))
PY
if python3 "$S/validate.py" "$WORK/two-promises.json" > "$WORK/two.out"; then echo "FAIL: a claim in two promises passed"; exit 1; fi
grep -q "claim C01: in 2 promises" "$WORK/two.out"
if python3 "$S/validate.py" "$WORK/no-promise.json" > "$WORK/none.out"; then echo "FAIL: a claim in no promise passed"; exit 1; fi
grep -q "claim C02: in no promise" "$WORK/none.out"
echo "validate refuses a claim in two promises and a claim in none"

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

step "explain: PR-body section, the level ladder, HTML"
EXTRA="$FIX/explain.json"
python3 "$S/explain.py" --map "$MAP" --repo "$REPO" --out "$WORK/explain" --extra "$EXTRA"

step "explain: the build refuses an ID in level 1, an undefined term, and a diagram with one mode"
python3 - "$EXTRA" "$MAP" "$WORK" <<'PY'
import json, sys
extra, data, work = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), sys.argv[3]
leak = json.loads(json.dumps(extra)); leak["story"]["trust"] = "Claim C01 is Proven, and `withdraw` checks it."
json.dump(leak, open(f"{work}/leak.json", "w"))
term = json.loads(json.dumps(extra)); term["story"]["problem"] = "Before this PR, the ZQX ledger let a withdrawal take the balance below zero."
json.dump(term, open(f"{work}/term.json", "w"))
mode = json.loads(json.dumps(extra)); del mode["diagrams"]["loop"]["detailed"]
json.dump(mode, open(f"{work}/mode.json", "w"))
PY
for case in "leak:the ID C01 is visible" "term:does not define: ZQX" "mode:has no detailed mode"; do
  name="${case%%:*}"; want="${case#*:}"
  if python3 "$S/explain.py" --map "$MAP" --repo "$REPO" --out "$WORK/bad-$name" --extra "$WORK/$name.json" 2> "$WORK/$name.err"; then
    echo "FAIL: explain.py accepted the $name case"; exit 1
  fi
  grep -q "$want" "$WORK/$name.err" || { echo "FAIL: the $name case failed for another reason:"; cat "$WORK/$name.err"; exit 1; }
done
echo "explain.py refuses a visible ID, an undefined term and a one-mode diagram"

# UNDERSTANDO_VE_RUNTIME pins an Artifacture checkout. explain.py reads it too.
if [ -n "${UNDERSTANDO_VE_RUNTIME:-}" ]; then
  VE="$UNDERSTANDO_VE_RUNTIME"
else
  VE="$(dirname "$(readlink -f "$HOME/.claude/skills/visual-explainer/SKILL.md" 2>/dev/null || echo "$HOME/.claude/skills/visual-explainer/SKILL.md")")"
fi
node "$VE/scripts/artifacture.mjs" export "$WORK/explain/explainer.mdx" --out "$WORK/explain/explainer.html"
test -s "$WORK/explain/explainer.html"
python3 - "$MAP" "$WORK/explain" <<'PY'
# One self-contained MDX unit per level. Each claim is in exactly one promise, has one claim block,
# and its plain sentence shows once on the whole page.
import json, pathlib, re, sys
data = json.load(open(sys.argv[1]))
out = pathlib.Path(sys.argv[2])
names = ["01-story", "02-loop", "03-change", "04-promises", "05-verifiers", "06-unclaimed", "07-tradeoffs", "08-exercises", "09-glossary"]
entry = (out / "explainer.mdx").read_text()
texts = {}
for n in names:
    f = out / "chapters" / f"{n}.mdx"
    if not f.is_file():
        sys.exit(f"FAIL: missing level file {n}")
    texts[n] = f.read_text()
    if "visual-explainer-mdx/components" not in texts[n].split("\n", 2)[1] or f"./chapters/{n}.mdx" not in entry:
        sys.exit(f"FAIL: level {n} does not import its components, or the entry does not import it")
member = {}
for p in data["promises"]:
    for cid in p["claims"]:
        member.setdefault(cid, []).append(p["id"])
blob = "\n".join(texts.values())
for c in data["claims"]:
    if len(member.get(c["id"], [])) != 1:
        sys.exit(f"FAIL: {c['id']} is in {member.get(c['id'], [])}, not in exactly one promise")
    anchor = 'id={"claim-' + c["id"].lower() + '"}'
    if texts["04-promises"].count(anchor) != 1:
        sys.exit(f"FAIL: {c['id']} has no single claim block in the promises level")
    said = json.dumps(c["plain"]["what"], ensure_ascii=False)[1:-1]
    if blob.count(said) != 1:
        sys.exit(f"FAIL: the sentence of {c['id']} shows {blob.count(said)} times; it must show once")
print(f"{len(names)} level units; each of the {len(data['claims'])} claims is in one promise, with one block and one sentence")
PY
# The rendered page: default themes only, and the ladder rules in a real browser.
node - "$VE" "$WORK/explain/explainer.html" "$MAP" <<'JS'
const path = require('node:path');
const fs = require('node:fs');
const [ve, html, mapPath] = process.argv.slice(2);
const data = JSON.parse(fs.readFileSync(mapPath, 'utf8'));
const { chromium } = require(require.resolve('playwright', { paths: [ve] }));
const fail = (message) => { console.error('FAIL: ' + message); process.exit(1); };
const ids = [...data.claims, ...data.verifiers, ...data.controls].map((x) => x.id);
const codeLike = /`|\b[a-z][a-z0-9]*_[a-z0-9_]+\b|\b[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*\b|\b[a-z]+[A-Z][A-Za-z0-9]*\b|\b[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]+\b|\w\(\)/;
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await page.goto('file://' + path.resolve(html), { waitUntil: 'load' });
    await page.waitForSelector('main.ve-shell');
    const got = await page.evaluate(() => ({
      styles: document.querySelectorAll('#root style').length,
      presets: [...new Set([...document.querySelectorAll('[data-ve-preset]')].map((e) => e.dataset.vePreset))],
    }));
    if (got.styles || got.presets.join() !== 'iso') fail(`the explainer has ${got.styles} page <style> elements and presets [${got.presets}]; want 0 and [iso]`);
    console.log('the explainer has no page <style> and uses only the iso preset');

    // Levels 1-3: the text a reader sees without opening anything (tables aside) holds no ID and no code name.
    const shown = async () => page.evaluate(() => ['story', 'loop', 'change'].map((id) => {
      const skip = '[data-ve-data-table], details:not([open]) > .ve-disclosure-body, [data-ve-variant="mobile"]';
      const walker = document.createTreeWalker(document.getElementById(id), NodeFilter.SHOW_TEXT);
      const parts = [];
      for (let node = walker.nextNode(); node; node = walker.nextNode()) if (!node.parentElement.closest(skip)) parts.push(node.textContent);
      return [id, parts.join(' ')];
    }));
    for (const [id, text] of await shown()) {
      const id_ = ids.find((x) => new RegExp(`(^|[^\\w-])${x}([^\\w-]|$)`).test(text));
      if (id_) fail(`level ${id} shows the ID ${id_}`);
      const code = text.match(codeLike);
      if (code) fail(`level ${id} shows the code name "${code[0]}"`);
    }
    console.log('levels 1-3 show no ID and no code name outside tables and collapsed blocks');

    // Each architecture diagram renders both modes; the mode is shared and remembered.
    const diagrams = page.locator('[data-ve-diagram-modes]');
    const count = await diagrams.count();
    if (count < 2) fail(`want the story and loop diagrams in two modes, found ${count}`);
    const labels = async () => page.$$eval('[data-ve-diagram-modes] [data-ve-variant="desktop"] svg text', (t) => t.map((x) => x.textContent).join(' | '));
    const simple = await labels();
    if (codeLike.test(simple)) fail(`the Simple mode shows a code name: ${simple.match(codeLike)[0]}`);
    await diagrams.first().getByLabel('Detailed').check();
    const modes = await page.$$eval('[data-ve-diagram-modes]', (d) => d.map((x) => x.dataset.veMode));
    if (modes.some((m) => m !== 'detailed')) fail(`one switch must set every diagram: ${modes}`);
    const detailed = await labels();
    if (detailed === simple || !codeLike.test(detailed)) fail('the Detailed mode must name real code');
    await page.reload({ waitUntil: 'load' });
    await page.waitForSelector('[data-ve-diagram-modes]');
    if ((await page.getAttribute('[data-ve-diagram-modes]', 'data-ve-mode')) !== 'detailed') fail('the page did not remember the Detailed mode');
    console.log(`${count} diagrams render a Simple and a Detailed mode, and the page remembers the choice`);

    // The glossary is a level of its own, in the rail; a term in the text shows its definition.
    const terms = await page.$$eval('#glossary dt', (t) => t.map((x) => x.textContent));
    for (const want of ['Overdraft', 'Balance', 'Proven', 'PR']) if (!terms.includes(want)) fail(`the glossary has no ${want}: ${terms}`);
    if (!(await page.$('.ve-chapter-list a[href="#glossary-section"]'))) fail('the rail has no Glossary entry');
    const term = page.locator('#story .ve-term').first();
    await term.focus();
    if (!(await term.locator('[role="tooltip"]').isVisible())) fail('a focused term shows no definition');
    console.log(`the glossary holds ${terms.length} terms and is in the rail; a focused term shows its definition`);

    // The merge verdict: first in the story, inside the first screen, each item a link to a promise.
    const verdict = await page.evaluate(() => {
      const line = document.querySelector('[data-merge-verdict]');
      const first = document.querySelector('#story .ve-section-body > *');
      return line && { form: line.dataset.mergeVerdict, top: line.getBoundingClientRect().top, first: first.contains(line),
        links: [...document.querySelectorAll('[data-merge-items] a, [data-merge-verdict] ~ p a')].map((a) => a.getAttribute('href')) };
    });
    const promiseIds = data.promises.map((p) => '#promise-' + p.id.toLowerCase());
    if (!verdict || !verdict.first || verdict.top > 900) fail(`the merge verdict is not first in the first screen: ${JSON.stringify(verdict)}`);
    if (verdict.form !== 'ready' && (!verdict.links.length || verdict.links.some((h) => !promiseIds.includes(h) && h !== '#story-ready' && !h.startsWith('#claim-')))) fail(`a merge item does not link to a promise: ${verdict.links}`);
    console.log(`the merge verdict (${verdict.form}) is first in the first screen and links to ${verdict.links.length} promises`);

    // Reader copy: no "red" or "green" outside code, and no ID in the prose of levels 4, 5 and 7.
    const prose = await page.evaluate(() => {
      const skip = 'pre, code, [data-ve-code-block], [data-ve-data-table], .ve-terminal, details:not([open]) > .ve-disclosure-body, .ve-disclosure-meta, [role="tooltip"]';
      const text = (root) => { const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT); const out = [];
        for (let n = w.nextNode(); n; n = w.nextNode()) if (!n.parentElement.closest(skip)) out.push(n.textContent); return out.join(' '); };
      return { all: text(document.querySelector('main')), levels: ['promises', 'verifiers', 'tradeoffs'].map((id) => [id, text(document.getElementById(id))]) };
    });
    const colour = prose.all.match(/\b(red|green)\b/i);
    if (colour) fail(`reader copy says "${colour[0]}": ${prose.all.slice(Math.max(0, colour.index - 60), colour.index + 40)}`);
    for (const [id, text] of prose.levels) {
      const leak = ids.find((x) => new RegExp(`(^|[^\\w-])${x}([^\\w-]|$)`).test(text));
      if (leak) fail(`level ${id} shows the ID ${leak} in its prose`);
    }
    console.log('reader copy has no red or green, and levels 4, 5 and 7 show no ID in their prose');

    // Keyboard: the first tab stop is the skip link, and it moves focus to the content.
    await page.goto('file://' + path.resolve(html), { waitUntil: 'load' });
    await page.waitForSelector('main.ve-shell');
    await page.keyboard.press('Tab');
    if ((await page.evaluate(() => document.activeElement?.textContent)) !== 'Skip to content') fail('the first tab stop is not the skip link');
    console.log('the first tab stop is the skip link');

    // No diagram is wider than its column.
    const wide = await page.$$eval('[data-ve-variant="desktop"]', (vs) => vs.filter((v) => v.offsetParent).map((v) => [v.scrollWidth, v.clientWidth]).filter(([s, c]) => s > c + 1));
    if (wide.length) fail(`a diagram overflows its column: ${JSON.stringify(wide)}`);
    console.log('no diagram overflows its column');

    // A deep link into a closed claim opens it and its promise, and puts its headline in view.
    await page.goto('file://' + path.resolve(html) + '#claim-c02', { waitUntil: 'load' });
    await page.waitForFunction(() => { const c = document.getElementById('claim-c02'); return c && c.open && c.parentElement.closest('details').open; });
    await page.waitForTimeout(400);
    const top = await page.$eval('#claim-c02', (c) => c.getBoundingClientRect().top);
    if (top < 0 || top > 200) fail(`the deep link to claim C02 puts its headline at ${top}px`);
    // Opening a block writes its link; a reload keeps it open.
    await page.click('#claim-c01 > summary .ve-disclosure-label');
    await page.waitForFunction(() => location.hash === '#claim-c01');
    await page.reload({ waitUntil: 'load' });
    await page.waitForFunction(() => document.getElementById('claim-c01')?.open);
    console.log(`a deep link opens claim C02 with its headline at ${Math.round(top)}px; an open block writes its link and stays open on reload`);

    // Unclaimed changes: the file that the fixture adds without a claim.
    const unclaimed = await page.$eval('#unclaimed', (s) => s.innerText);
    if (!unclaimed.includes('bin/report.py')) fail('the unclaimed panel does not list bin/report.py');
    if (unclaimed.includes('wallet/fees.py')) fail('the unclaimed panel lists wallet/fees.py, which a claim cites');
    console.log('the unclaimed panel lists bin/report.py');
  } finally {
    await browser.close();
  }
})();
JS
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
step "refs: symbol anchors, snippet, permalinks, anchor controls, the guard and drift (tests/refs-e2e.sh)"
WORK="$WORK" REPO="$REPO" MAP="$MAP" HEAD="$HEAD" FIX="$FIX" bash "$ROOT/tests/refs-e2e.sh"
step "mode: the CLI verbs, the gates and the ledger (tests/mode-e2e.sh)"
WORK="$WORK" REPO="$REPO" MAP="$MAP" HEAD="$HEAD" FIX="$FIX" bash "$ROOT/tests/mode-e2e.sh"

if command -v lake >/dev/null && command -v java >/dev/null && [ -f "${UNDERSTANDO_TLA2TOOLS:-$HOME/.understando/tools/tla2tools.jar}" ]; then
  step "formal: the formalize sub-skills (tests/formal/e2e.sh)"
  bash "$ROOT/tests/formal/e2e.sh" | tail -5
else
  step "formal: skipped, because lake, java or tla2tools.jar is missing (tests/formal/e2e.sh needs them)"
fi

echo
echo "PASS: understando e2e on the fixture"
