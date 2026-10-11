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
# The visual-explainer runtime: ve_runtime in ~/.understando/config.toml (UNDERSTANDO_VE_RUNTIME overrides it).
# Read it before the fake homes below; explain.py and the later steps get it through the variable.
UNDERSTANDO_VE_RUNTIME="${UNDERSTANDO_VE_RUNTIME:-$(python3 "$S/config.py" ve-runtime || true)}"
[ -n "$UNDERSTANDO_VE_RUNTIME" ] && export UNDERSTANDO_VE_RUNTIME || unset UNDERSTANDO_VE_RUNTIME
JAVA_FOUND="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import ctx; print(ctx.java_bin() or "")' "$S")"
# The mode state of the user's own session must not leak into the fixture run.
export UNDERSTANDO_HOME="$WORK/uhome0"
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
python3 - "$MAP" "$FIX/promises.json" "$FIX/names.json" <<'PY'
# The map step writes three to six promises after the scan, so each claim, also each added one,
# belongs to exactly one promise. The agent also writes the plain name of each added claim.
import json, sys
data = json.load(open(sys.argv[1]))
data["promises"] = json.load(open(sys.argv[2]))
for claim in data["claims"]:
    claim.setdefault("name", json.load(open(sys.argv[3])).get(claim["id"]))
json.dump(data, open(sys.argv[1], "w"), indent=2)
PY
python3 "$S/mechanical.py" --map "$MAP" --repo "$REPO"
# The old shape (each verifier lists its claims) stays readable for one release: keep a copy.
cp "$MAP" "$WORK/old-shape.json"

step "map: the fixture migrates to the new shape (promise -> claim -> check)"
python3 "$S/onto.py" upgrade "$MAP"
python3 - "$MAP" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
assert data["schema_version"] == 2, data["schema_version"]
checks = {c["id"]: c["checks"] for c in data["claims"]}
assert checks["C01"] == ["V01", "V03"] and checks["C02"] == ["V02"], checks
none = {v["id"]: v for v in data["verifiers"] if v["kind"] == "none"}
gap = [c for c in data["claims"] if not any(v["id"] in c["checks"] for v in data["verifiers"] if v["kind"] != "none")]
assert sorted(c["id"] for c in gap) == ["C03", "C04"], [c["id"] for c in gap]
assert all(len(c["checks"]) == 1 and c["checks"][0] in none for c in gap), "a claim with no tool check lists one check of kind none"
assert all(sorted(v["claims"]) == sorted(c["id"] for c in data["claims"] if v["id"] in c["checks"]) for v in data["verifiers"]), "the verifier lists mirror the claim lists"
print(f"the fixture is in shape 2: {len(data['claims'])} claims list their checks; {len(none)} claims with no tool check list a check of kind none")
PY
python3 "$S/validate.py" "$MAP"

step "validate: an orphan check and a claim with no checks fail"
python3 - "$MAP" "$WORK/orphan.json" "$WORK/no-checks.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
orphan = json.loads(json.dumps(data))
orphan["verifiers"].append({**orphan["verifiers"][0], "id": "V99", "claims": ["C01"]})
empty = json.loads(json.dumps(data))
next(c for c in empty["claims"] if c["id"] == "C07")["checks"] = []
json.dump(orphan, open(sys.argv[2], "w")); json.dump(empty, open(sys.argv[3], "w"))
PY
if python3 "$S/validate.py" "$WORK/orphan.json" > "$WORK/orphan.out"; then echo "FAIL: an orphan check passed"; exit 1; fi
grep -q "check V99: no claim lists it" "$WORK/orphan.out"
if python3 "$S/validate.py" "$WORK/no-checks.json" > "$WORK/no-checks.out"; then echo "FAIL: a claim with no checks passed"; exit 1; fi
grep -q "claim C07: has no checks" "$WORK/no-checks.out"
echo "validate refuses a check that no claim lists and a claim with no checks"

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

step "validate: a claim, a plain text or a name that is not strict STE (asd-ste100) fails"
python3 - "$MAP" "$WORK/not-ste.json" "$WORK/not-ste-name.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
claim = json.loads(json.dumps(data)); claim["claims"][0]["text"] += "; the rule also holds when the balance is zero"
name = json.loads(json.dumps(data)); name["claims"][1]["plain"]["what"] = "A seamless and robust refusal of overdrafts."
json.dump(claim, open(sys.argv[2], "w")); json.dump(name, open(sys.argv[3], "w"))
PY
python3 "$S/validate.py" "$MAP" > /dev/null
if python3 "$S/validate.py" "$WORK/not-ste.json" > "$WORK/not-ste.out"; then echo "FAIL: a claim with a semicolon passed"; exit 1; fi
grep -q "not strict STE: semicolon" "$WORK/not-ste.out"
if python3 "$S/validate.py" "$WORK/not-ste-name.json" > "$WORK/not-ste-name.out"; then echo "FAIL: a plain text with a marketing word passed"; exit 1; fi
grep -q "not strict STE: marketing-adjective" "$WORK/not-ste-name.out"
echo "validate refuses a claim with a semicolon and a plain text with a marketing word"

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

step "explain: the agent's MDX through the visual-explainer pipeline: refs, the pre-rendered HTML, the PR section"
# The explain step writes explainer.mdx next to the map (the narrative and the data components).
cp "$FIX/explainer.mdx" "$WORK/explainer.mdx"
EXTRA="$FIX/explain.json"
# The pinned runtime (above); without one, the repo behind the visual-explainer skill link.
if [ -n "${UNDERSTANDO_VE_RUNTIME:-}" ]; then
  VE="$UNDERSTANDO_VE_RUNTIME"
else
  VE="$(dirname "$(readlink -f "$HOME/.claude/skills/visual-explainer/SKILL.md" 2>/dev/null || echo "$HOME/.claude/skills/visual-explainer/SKILL.md")")"
fi
export UNDERSTANDO_VE_RUNTIME="$VE"
python3 "$S/explain.py" --map "$MAP" --repo "$REPO" --out "$WORK/explain" --extra "$EXTRA"
test -s "$WORK/explain/explainer.html"

step "explain: the export refuses an ID in the prose, an undefined term, a one-mode diagram, a weak promise without an action, and pasted code"
python3 - "$FIX" "$MAP" "$WORK" <<'PY'
import json, pathlib, sys
fix, data, work = pathlib.Path(sys.argv[1]), json.load(open(sys.argv[2])), pathlib.Path(sys.argv[3])
mdx, extra = (fix / "explainer.mdx").read_text(), json.loads((fix / "explain.json").read_text())
story = "A planted bug proves the overdraft rule."
cases = {
    "leak": (mdx.replace(story, "Claim C01 is Proven, and `withdraw` checks it."), extra, data),
    "term": (mdx.replace(story, "The ZQX ledger lets a withdrawal take the balance below zero."), extra, data),
    "mode": (mdx, {**extra, "diagrams": {**extra["diagrams"], "loop": {k: v for k, v in extra["diagrams"]["loop"].items() if k != "detailed"}}}, data),
    "action": (mdx, extra, {**data, "promises": [{k: v for k, v in p.items() if k != "reviewer_action"} if p["id"] == "P4" else p for p in data["promises"]]}),
    "pasted": (mdx.replace("Next: [see how one withdrawal runs](#ch-2).", "```python\nclass OverdraftError(ValueError):\n    pass\n```\n\nNext: [see how one withdrawal runs](#ch-2)."), extra, data),
}
for name, (m, e, d) in cases.items():
    out = work / f"bad-{name}"
    out.mkdir(exist_ok=True)
    (out / "explainer.mdx").write_text(m)
    (out / "explain.json").write_text(json.dumps(e))
    (out / "trust-map.json").write_text(json.dumps(d))
PY
for case in "leak:the ID C01 is in the narrative prose" "term:does not define: ZQX" "mode:has no detailed mode" "action:needs a reviewer_action" "pasted:pasted code from wallet/core.py"; do
  name="${case%%:*}"; want="${case#*:}"; B="$WORK/bad-$name"
  if python3 "$S/explain.py" --map "$B/trust-map.json" --repo "$REPO" --out "$B" --extra "$B/explain.json" > "$B/out.txt" 2>&1; then
    echo "FAIL: the export accepted the $name case"; exit 1
  fi
  grep -q "$want" "$B/out.txt" || { echo "FAIL: the $name case failed for another reason:"; cat "$B/out.txt"; exit 1; }
done
echo "the export refuses a visible ID, an undefined term, a one-mode diagram, a weak promise without an action and pasted code"

python3 - "$MAP" "$WORK/explain" <<'PY'
# The refs, the stamp and the pre-render: each claim has one block, and the page names its map.
import hashlib, html as h, json, pathlib, re, sys
data = json.load(open(sys.argv[1]))
out = pathlib.Path(sys.argv[2])
refs = json.loads((out / "refs.resolved.json").read_text())
assert refs["schema"] == 2 and refs["head"] == data["head"], refs.get("head")
assert all(k["id"] in refs["controls"] for k in data["controls"]), "a control has no patch"
html = (out / "explainer.html").read_text()
assert f'<meta name="ve-trust-map-head" content="{data["head"]}">' in html, "no head stamp"
assert f'<meta name="ve-trust-map-sha256" content="{hashlib.sha256((out / "trust-map.json").read_bytes()).hexdigest()}">' in html, "no map hash stamp"
root = html.split('<div id="root">', 1)[1]
text = h.unescape(re.sub(r"<[^>]+>", "", root))
for c in data["claims"]:
    n = root.count(f'id="claim-{c["id"].lower()}"')
    if n != 1:
        sys.exit(f"FAIL: {c['id']} has {n} claim blocks in the pre-render")
for p in data["promises"]:
    assert " ".join(p["sentence"].split()[:4]) in text, f"the pre-render lacks the promise {p['id']}"
print(f"refs at the head, the map stamped, and each of the {len(data['claims'])} claims in one pre-rendered block")
PY
# The rendered page: default themes only, and the level rules in a real browser.
node - "$VE" "$WORK/explain/explainer.html" "$MAP" <<'JS'
const path = require('node:path');
const fs = require('node:fs');
const [ve, html, mapPath] = process.argv.slice(2);
const data = JSON.parse(fs.readFileSync(mapPath, 'utf8'));
const { chromium } = require(require.resolve('playwright', { paths: [ve] }));
const fail = (message) => { console.error('FAIL: ' + message); process.exit(1); };
const ids = [...data.claims, ...data.verifiers, ...data.controls].map((x) => x.id);
const url = 'file://' + path.resolve(html);
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    // Without JavaScript: the text, the merge verdict, the promises and the claim text show, and a deep link opens its claim.
    const off = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 1280, height: 900 } });
    const still = await off.newPage();
    await still.goto(url + '#claim-c02', { waitUntil: 'load' });
    const text = await still.innerText('main');
    for (const want of ['things to review', data.promises[0].label, data.claims[0].name ?? data.claims[0].plain.what.split('`')[0].trim()]) if (!text.toLowerCase().includes(want.toLowerCase())) fail(`without JavaScript the page lacks "${want}"`);
    if (!(await still.$eval('#claim-c02 .ve-disclosure-body', (b) => b.getBoundingClientRect().height > 0))) fail('without JavaScript the deep link does not show claim C02');
    await off.close();
    console.log('without JavaScript the page shows the merge verdict, the promises and the claims, and a deep link shows its claim');

    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const errors = [];
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto(url, { waitUntil: 'load' });
    await page.waitForSelector('main.ve-shell');
    await page.waitForTimeout(300);
    if (errors.length) fail(`the page logs errors (hydration): ${errors.join(' | ').slice(0, 400)}`);
    const got = await page.evaluate(() => ({
      styles: document.querySelectorAll('#root style').length,
      presets: [...new Set([...document.querySelectorAll('[data-ve-preset]')].map((e) => e.dataset.vePreset))],
      levels: [...document.querySelectorAll('main section.ve-section[id]')].map((s) => s.id).join(','),
    }));
    if (got.styles || got.presets.join() !== 'iso') fail(`the explainer has ${got.styles} page <style> elements and presets [${got.presets}]; want 0 and [iso]`);
    if (got.levels !== 'ch-0,ch-1,ch-2,ch-3,ch-4,ch-5,ch-6,ch-7,ch-8,ch-9') fail(`the chapter ids are ${got.levels}`);
    // The old level anchors still land: each is an alias in the chapter that holds its level.
    for (const old of ['story', 'why', 'loop', 'changed', 'unclaimed', 'verifiers', 'promises', 'tradeoffs', 'exercises', 'glossary']) {
      if (!(await page.$(`section.ve-section > #${old}`))) fail(`the old anchor #${old} has no target`);
    }
    console.log('the page hydrates with no error, has no page <style>, uses only the iso preset, has the chapter ids and keeps the old anchors');

    // Read as one page from here: every chapter shows, so each figure can be measured.
    await page.evaluate(() => localStorage.setItem('ve-read-mode:' + location.pathname, 'one'));
    await page.reload({ waitUntil: 'load' });
    await page.waitForSelector('main[data-ve-paged="one"]');
    // Each architecture diagram renders both modes; the mode is shared and remembered.
    const codeLike = /`|\b[a-z][a-z0-9]*_[a-z0-9_]+\b|\b[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*\b|\b[a-z]+[A-Z][A-Za-z0-9]*\b|\b[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]+\b|\w\(\)/;
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
    console.log(`${count} diagrams render a Simple and a Detailed mode`);

    // The glossary is a level of its own, in the rail; a term in the text shows its definition.
    const terms = await page.$$eval('[data-ve-glossary] dt', (t) => t.map((x) => x.textContent));
    for (const want of ['Overdraft', 'Balance', 'Proven', 'PR']) if (!terms.includes(want)) fail(`the glossary has no ${want}: ${terms}`);
    if (!(await page.$('.ve-chapter-list a[href="#verdict-glossary"]')) && !(await page.$('.ve-chapter-list a[href="#ch-8"]'))) fail('the rail has no way to the glossary');
    const term = page.locator('#ch-0 .ve-term').first();
    await term.focus();
    if (!(await term.locator('[role="tooltip"]').isVisible())) fail('a focused term shows no definition');
    console.log(`the glossary holds ${terms.length} terms and is in the rail; a focused term shows its definition`);

    // The merge state: #merge, in the start chapter, inside the first screen, each item a link to its checklist item.
    const verdict = await page.evaluate(() => {
      const line = document.querySelector('#merge [data-merge-verdict]');
      return line && { form: line.dataset.mergeVerdict, top: line.getBoundingClientRect().top, first: Boolean(line.closest('#ch-0')),
        links: [...document.querySelectorAll('[data-merge-items] a')].map((a) => a.getAttribute('href')) };
    });
    const targets = [...data.promises.map((p) => '#promise-' + p.id.toLowerCase()), '#review-story-ready', '#review-unclaimed'];
    if (!verdict || !verdict.first || verdict.top > 900) fail(`the merge state is not in the first screen: ${JSON.stringify(verdict)}`);
    if (verdict.form !== 'ready' && (!verdict.links.length || verdict.links.some((h) => !targets.includes(h) && !h.startsWith('#claim-')))) fail(`a merge item does not link to a promise: ${verdict.links}`);
    console.log(`the merge verdict (${verdict.form}) is first in the first screen and links to ${verdict.links.length} targets`);

    // Reader copy: no "red" or "green" outside code, and no ID in the prose of the narrative and the verify level.
    const prose = await page.evaluate(() => {
      const skip = 'pre, code, [data-ve-code-block], [data-ve-data-table], .ve-terminal, details:not([open]) > .ve-disclosure-body, .ve-disclosure-meta, [role="tooltip"], [data-ve-glossary]';
      const text = (root) => { const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT); const out = [];
        for (let n = w.nextNode(); n; n = w.nextNode()) if (!n.parentElement.closest(skip)) out.push(n.textContent); return out.join(' '); };
      return { all: text(document.querySelector('main')), levels: ['ch-0', 'ch-1', 'ch-2', 'ch-3', 'ch-4', 'ch-8'].map((id) => [id, text(document.getElementById(id))]),
        first: document.querySelector('#ch-4 [data-ve-trust="verifiers"] > *')?.textContent };
    });
    const colour = prose.all.match(/\b(red|green)\b/i);
    if (colour) fail(`reader copy says "${colour[0]}": ${prose.all.slice(Math.max(0, colour.index - 60), colour.index + 40)}`);
    for (const [id, text] of prose.levels) {
      const leak = ids.find((x) => new RegExp(`(^|[^\\w-])${x}([^\\w-]|$)`).test(text));
      if (leak) fail(`level ${id} shows the ID ${leak} in its prose`);
    }
    if (!/\d+ of \d+ checks caught their planted bug/.test(prose.first ?? '')) fail(`the verify level does not open with its result: ${prose.first}`);
    console.log('reader copy has no red or green, the prose shows no ID, and the verify level opens with its result');

    // Keyboard: the first tab stop is the skip link.
    await page.goto(url, { waitUntil: 'load' });
    await page.waitForSelector('main.ve-shell');
    await page.keyboard.press('Tab');
    if ((await page.evaluate(() => document.activeElement?.textContent)) !== 'Skip to content') fail('the first tab stop is not the skip link');
    console.log('the first tab stop is the skip link');

    // No diagram is wider than its column.
    const wide = await page.$$eval('[data-ve-variant="desktop"]', (vs) => vs.filter((v) => v.offsetParent).map((v) => [v.scrollWidth, v.clientWidth]).filter(([s, c]) => s > c + 1));
    if (wide.length) fail(`a diagram overflows its column: ${JSON.stringify(wide)}`);
    console.log('no diagram overflows its column');

    // A deep link into a closed claim shows its chapter, opens it and each block around it, and puts its headline in view.
    await page.goto(url + '#claim-c01', { waitUntil: 'load' });
    await page.waitForFunction(() => { const c = document.getElementById('claim-c01'); return c && c.open && !c.closest('section').hidden && [...document.querySelectorAll('details')].filter((d) => d.contains(c)).every((d) => d.open); });
    await page.waitForTimeout(400);
    const top = await page.$eval('#claim-c01', (c) => c.getBoundingClientRect().top);
    if (top < 0 || top > 200) fail(`the deep link to claim C01 puts its headline at ${top}px`);
    await page.click('#promise-p4 > summary .ve-disclosure-label');
    await page.waitForFunction(() => location.hash === '#promise-p4');
    await page.reload({ waitUntil: 'load' });
    await page.waitForFunction(() => document.getElementById('promise-p4')?.open);
    console.log(`a deep link opens claim C01 with its headline at ${Math.round(top)}px; an open block writes its link and stays open on reload`);

    // What changed: the file that the fixture adds without a claim, with its status, and a file that a claim protects.
    await page.goto(url + '#ch-3', { waitUntil: 'load' });
    await page.waitForFunction(() => !document.getElementById('ch-3').hidden);
    const report = await page.$eval('[data-ve-spine-file="bin/report.py"]', (s) => s.innerText);
    if (!/Low risk: skim|No claim/.test(report)) fail(`bin/report.py has no protection status: ${report}`);
    const fees = await page.$eval('[data-ve-spine-file="wallet/fees.py"]', (s) => s.innerText);
    if (!/Protected by 1 claim/.test(fees)) fail(`wallet/fees.py does not show the claim that protects it: ${fees}`);
    const spine = await page.$eval('#ch-3', (s) => s.innerText);
    if (!/changed files? ha(s|ve) no claim/.test(spine)) fail('what changed has no summary line of the unclaimed files');
    console.log('what changed shows bin/report.py with its status, wallet/fees.py with its claim, and the summary');
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
states = {v["id"]: v["state"] for v in got["verifiers"] if v["kind"] != "none"}
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
step "onto: the grouping lint, plain names, coverage, close --add-claim and the old shape (tests/onto-e2e.sh)"
WORK="$WORK" REPO="$REPO" MAP="$MAP" HEAD="$HEAD" FIX="$FIX" bash "$ROOT/tests/onto-e2e.sh"
step "refs: symbol anchors, snippet, permalinks, anchor controls, the guard and drift (tests/refs-e2e.sh)"
WORK="$WORK" REPO="$REPO" MAP="$MAP" HEAD="$HEAD" FIX="$FIX" bash "$ROOT/tests/refs-e2e.sh"
step "mode: the CLI verbs, the gates and the ledger (tests/mode-e2e.sh)"
WORK="$WORK" REPO="$REPO" MAP="$MAP" HEAD="$HEAD" FIX="$FIX" bash "$ROOT/tests/mode-e2e.sh"

step "store: the runs root, the run-state guard, publish, the review cache, doctor and java (tests/store-e2e.sh)"
WORK="$WORK" REPO="$REPO" MAP="$MAP" HEAD="$HEAD" FIX="$FIX" bash "$ROOT/tests/store-e2e.sh"

if command -v lake >/dev/null && [ -n "$JAVA_FOUND" ] && [ -f "${UNDERSTANDO_TLA2TOOLS:-$HOME/.understando/tools/tla2tools.jar}" ]; then
  step "formal: the formalize sub-skills (tests/formal/e2e.sh)"
  bash "$ROOT/tests/formal/e2e.sh" | tail -5
else
  step "formal: skipped, because lake, java or tla2tools.jar is missing (tests/formal/e2e.sh needs them)"
fi

echo
echo "PASS: understando e2e on the fixture"
