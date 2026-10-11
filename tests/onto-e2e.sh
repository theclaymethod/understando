#!/usr/bin/env bash
# End-to-end test of the review ontology: promise -> claim -> check. tests/e2e.sh calls it after the
# explain step, with WORK, REPO, MAP, HEAD and FIX set. It drives the real scripts and the CLI:
#   - the grouping lint suggests the merge that the merge rule gives;
#   - a mechanical name is flagged, and map refuses a missing name;
#   - coverage records the files that a check runs, and a file that a check runs counts as covered;
#   - close --add-claim drafts a claim, attaches the checks that run the file, and offers a check;
#   - old-shape data (schema_version 1) still builds and renders.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$ROOT/tests/isolate.sh" onto
S="$ROOT/scripts"
U="$ROOT/bin/understando"
O="$WORK/onto"
mkdir -p "$O"
step() { printf '\n== %s\n' "$*"; }

step "onto: the grouping lint suggests the merge of two claims with the same promise, kind of check and action"
python3 - "$MAP" "$O/merge.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
v07 = next(v for v in data["verifiers"] if v["id"] == "V07")
k07 = next(k for k in data["controls"] if k["verifier"] == "V07")
data["verifiers"].append({**json.loads(json.dumps(v07)), "id": "V20", "name": "the currency test", "claims": ["C20"]})
data["controls"].append({**json.loads(json.dumps(k07)), "id": "K20", "verifier": "V20"})
c07 = next(c for c in data["claims"] if c["id"] == "C07")
data["claims"].append({**json.loads(json.dumps(c07)), "id": "C20", "name": "the currency in the denial", "text": "A denial message names the currency.",
                       "plain": {"what": "A denial message tells the person the currency.", "proof": "A unit test."}, "checks": ["V20"]})
next(p for p in data["promises"] if "C07" in p["claims"])["claims"].append("C20")
json.dump(data, open(sys.argv[2], "w"), indent=2)
PY
python3 "$S/verdicts.py" "$O/merge.json" > /dev/null
python3 "$S/onto.py" lint "$O/merge.json" | tee "$O/lint.txt"
grep -q "^merge: the amount in the denial and the currency in the denial have the same promise ('the private messages'), the same kind of check (unit)" "$O/lint.txt"
grep -q "(ref: C07, C20)" "$O/lint.txt"
if grep -q "C05, C06\|C06, C07" "$O/lint.txt"; then echo "FAIL: the lint suggests a merge of claims with different kinds of check"; exit 1; fi
grep -q "^budget: 9 claims; about 10 to 25 is the budget" "$O/lint.txt"
echo "the lint suggests the one merge that the rule gives, and warns about the budget"

step "onto: a mechanical name is flagged; map refuses a missing name"
python3 - "$MAP" "$O/names.json" "$O/unnamed/trust-map.json" <<'PY'
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(sys.argv[0]).resolve().parent))
data = json.load(open(sys.argv[1]))
bad = json.loads(json.dumps(data))
c01 = next(c for c in bad["claims"] if c["id"] == "C01")
c01["name"] = "the withdraw function stops when"   # the first words of plain.what, cut off
next(v for v in bad["verifiers"] if v["id"] == "V01")["name"] = "Unit check (unittest on test_core.py)"
next(v for v in bad["verifiers"] if v["id"] == "V07")["name"] = "the unittest of the denial"
json.dump(bad, open(sys.argv[2], "w"), indent=2)
none = json.loads(json.dumps(data))
del next(c for c in none["claims"] if c["id"] == "C05")["name"]
pathlib.Path(sys.argv[3]).parent.mkdir(parents=True, exist_ok=True)
json.dump(none, open(sys.argv[3], "w"), indent=2)
PY
python3 "$S/onto.py" lint "$O/names.json" | grep "^name:" | tee "$O/names.txt"
grep -q "the claim 'the withdraw function stops when' is not plain: it is the first words of the plain text, cut off" "$O/names.txt"
grep -q "the check 'Unit check (unittest on test_core.py)' is not plain: it holds a path or a file name" "$O/names.txt"
grep -q "the check 'the unittest of the denial' is not plain: it names a tool (unittest)" "$O/names.txt"
if grep -q "the overdraft refusal\|the denial amount test" "$O/names.txt"; then echo "FAIL: a plain name is flagged"; exit 1; fi
if "$U" --repo "$REPO" --run "$O/unnamed" map > "$O/unnamed.out" 2>&1; then echo "FAIL: map accepted a claim with no name"; cat "$O/unnamed.out"; exit 1; fi
grep -q "map: refuse: 1 items have no plain name: claim C05" "$O/unnamed.out"
echo "a cut of the plain text, a path and a tool name are flagged; map refuses a claim with no name"

step "coverage: a check that runs a file covers it"
R="$O/run"
mkdir -p "$R"
python3 - "$MAP" "$R/trust-map.json" "$O/edited/trust-map.json" <<'PY'
# Take away the code refs of the denial claims. With its control, the denial test covers
# messages.py by the control-edit rule; without its control, only the coverage record can.
import json, pathlib, sys
data = json.load(open(sys.argv[1]))
for c in data["claims"]:
    if c["id"] in ("C05", "C07"):
        c["code"] = []
pathlib.Path(sys.argv[3]).parent.mkdir(parents=True, exist_ok=True)
json.dump(data, open(sys.argv[3], "w"), indent=2)
data["controls"] = [k for k in data["controls"] if k["id"] != "K07"]
json.dump(data, open(sys.argv[2], "w"), indent=2)
PY
python3 "$S/verdicts.py" "$R/trust-map.json" > /dev/null
cp "$FIX/explain.json" "$R/explain.json"
python3 "$S/explain.py" --map "$R/trust-map.json" --repo "$REPO" --out "$O/before" --extra "$R/explain.json" --no-html > /dev/null
python3 "$S/explain.py" --map "$O/edited/trust-map.json" --repo "$REPO" --out "$O/edited" --extra "$R/explain.json" --no-html > /dev/null
"$U" --repo "$REPO" --run "$R" coverage | tee "$O/coverage.out"
grep -q "coverage V07: green" "$O/coverage.out"
python3 "$S/explain.py" --map "$R/trust-map.json" --repo "$REPO" --out "$O/after" --extra "$R/explain.json" --no-html > /dev/null
python3 - "$R/coverage.json" "$O/before/refs.resolved.json" "$O/after/refs.resolved.json" "$O/edited/refs.resolved.json" <<'PY'
import json, sys
cov = json.load(open(sys.argv[1]))
edited = {f["path"]: f for f in json.load(open(sys.argv[4]))["derived"]["unclaimed"]["files"]}
assert "wallet/messages.py" not in edited, "the control of the denial test edits messages.py, so its claim covers it"
assert "wallet/messages.py" in cov["checks"]["V07"]["files"], cov["checks"]["V07"]
assert "wallet/core.py" in cov["checks"]["V01"]["files"], cov["checks"]["V01"]
before = [f["path"] for f in json.load(open(sys.argv[2]))["derived"]["unclaimed"]["files"]]
after = [f["path"] for f in json.load(open(sys.argv[3]))["derived"]["unclaimed"]["files"]]
assert "wallet/messages.py" in before, f"without the coverage record, messages.py has no claim: {before}"
assert "wallet/messages.py" not in after, f"the denial test runs messages.py, so a claim covers it: {after}"
assert "bin/report.py" in after, after
print(f"wallet/messages.py: unclaimed before the coverage record, covered by the check that runs it after ({len(before)} -> {len(after)} unclaimed files)")
PY

step "close --add-claim: draft a claim for a file, attach the checks that run it, offer a check"
"$U" --repo "$REPO" --run "$R" close --add-claim wallet/messages.py | tee "$O/draft.out"
grep -q "The symbols that the file changes are denial" "$O/draft.out"
grep -q "The checks that run it are the denial amount test" "$O/draft.out"
"$U" --repo "$REPO" --run "$R" close --add-claim wallet/messages.py --name "the denial wording" \
  --text "A denial message names the amount and the balance." --promise P3 | tee "$O/added.out"
grep -q "Added the claim 'the denial wording' to the promise 'the private messages'" "$O/added.out"
grep -q "It has 1 check that runs the file: the denial amount test" "$O/added.out"
grep -q "Next: add a check" "$O/added.out"
python3 - "$R/trust-map.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
c = next(c for c in data["claims"] if c.get("name") == "the denial wording")
assert c["checks"] == ["V07"] and c["stated"] is False and c["code"][0]["path"] == "wallet/messages.py", c
assert c["id"] in next(p for p in data["promises"] if p["id"] == "P3")["claims"]
assert c["id"] in next(v for v in data["verifiers"] if v["id"] == "V07")["claims"]
print(f"close --add-claim added {c['id']} under P3 with the check that runs the file; it is {c['verdict']}")
PY
if "$U" --repo "$REPO" --run "$R" close --add-claim bin/report.py --name "report.py prints" --text "x" --promise P1 > "$O/badname.out"; then
  echo "FAIL: close accepted a name with a file name"; exit 1; fi
grep -q "is not plain: it holds a path or a file name" "$O/badname.out"
echo "close --add-claim refuses a name that holds a file name"

step "old shape: a schema_version 1 map still builds and renders"
python3 - "$MAP" "$O/old/trust-map.json" <<'PY'
import json, pathlib, sys
data = json.load(open(sys.argv[1]))
none = {v["id"] for v in data["verifiers"] if v["kind"] == "none"}
data["schema_version"] = 1
data["verifiers"] = [v for v in data["verifiers"] if v["id"] not in none]
for c in data["claims"]:
    c.pop("checks", None)
for p in data["promises"]:
    p.pop("name", None)
pathlib.Path(sys.argv[2]).parent.mkdir(parents=True, exist_ok=True)
json.dump(data, open(sys.argv[2], "w"), indent=2)
PY
python3 "$S/verdicts.py" "$O/old/trust-map.json" > /dev/null
python3 "$S/validate.py" "$O/old/trust-map.json"
cp "$FIX/explainer.mdx" "$O/old/explainer.mdx"
python3 "$S/explain.py" --map "$O/old/trust-map.json" --repo "$REPO" --out "$O/old" --extra "$FIX/explain.json" > /dev/null
python3 - "$O/old" "$MAP" <<'PY'
import json, pathlib, sys
out, new = pathlib.Path(sys.argv[1]), json.load(open(sys.argv[2]))
old = json.loads((out / "trust-map.json").read_text())
assert old["schema_version"] == 1
html = (out / "explainer.html").read_text()
for c in old["claims"]:
    assert html.count(f'id="claim-{c["id"].lower()}"') == 1, c["id"]
d = json.loads((out / "refs.resolved.json").read_text())["derived"]
assert d["claims"]["C01"]["summary"] == "2 checks: 2 caught their bug.", d["claims"]["C01"]["summary"]
assert {c["id"]: c["verdict"] for c in old["claims"]} == {c["id"]: c["verdict"] for c in new["claims"]}, "the shapes give different verdicts"
print(f"the old shape builds and renders each of its {len(old['claims'])} claims, with the same verdicts as the new shape")
PY
step "strength: a part is as strong as its strongest check, and a claim is as strong as its weakest part"
python3 - "$MAP" "$O/strength" <<'PY'
import json, pathlib, sys
data, out = json.load(open(sys.argv[1])), pathlib.Path(sys.argv[2])
out.mkdir(exist_ok=True)
# 1. A backup test next to the proof: the claim of the proof stays Formal.
backup = json.loads(json.dumps(data))
next(c for c in backup["claims"] if c["id"] == "C08")["checks"].append("V07")
next(v for v in backup["verifiers"] if v["id"] == "V07")["claims"].append("C08")
json.dump(backup, open(out / "backup.json", "w"), indent=2)
# 2. A missed bug: a second control that the contract check misses. The overdraft claim keeps its strength, with a flag.
missed = json.loads(json.dumps(data))
k03 = next(k for k in missed["controls"] if k["id"] == "K03")
missed["controls"].append({**json.loads(json.dumps(k03)), "id": "K30", "description": "Change a comment only.", "result": {**k03["result"], "status": "green", "exit": 0}})
json.dump(missed, open(out / "missed.json", "w"), indent=2)
# 3. A merged claim with an unproven part: the overdraft refusal (Proven) and the thread safety (Asserted).
proposal = {"claims": [], "promises": []}
owner = {cid: p["id"] for p in data["promises"] for cid in p["claims"]}
for c in data["claims"]:
    if c["id"] == "C04":
        continue
    row = {"id": c["id"], "promise": owner[c["id"]], "merges": [c["id"]], "name": c["name"], "text": c["text"], "plain": c["plain"]}
    if c["id"] == "C01":
        row.update({"merges": ["C01", "C04"], "name": "the safe overdraft refusal", "text": "The withdraw function refuses an overdraft, also with many threads."})
    proposal["claims"].append(row)
json.dump(proposal, open(out / "proposal.json", "w"), indent=2)
PY
python3 "$S/verdicts.py" "$O/strength/backup.json" > /dev/null
python3 "$S/verdicts.py" "$O/strength/missed.json" > /dev/null
python3 "$S/regroup.py" --map "$MAP" --proposal "$O/strength/proposal.json" --out "$O/strength/merged.json" > "$O/strength/proof.txt" || { cat "$O/strength/proof.txt"; exit 1; }
python3 - "$O/strength" "$ROOT/scripts" <<'PY'
import json, pathlib, sys
out = pathlib.Path(sys.argv[1]); sys.path.insert(0, sys.argv[2])
import derive
verdict = lambda f, cid: next(c for c in json.load(open(out / f))["claims"] if c["id"] == cid)["verdict"]  # noqa: E731
assert verdict("backup.json", "C08") == "Formal", "a backup test lowered the proof"
assert verdict("missed.json", "C01") == "Proven", "a missed bug lowered a part that another check proves"
rows = derive.claim_rows(json.load(open(out / "missed.json")))
assert rows["C01"]["flagged"]["text"] == "1 of 2 checks missed its bug: the contract format check. Fix it or drop it.", rows["C01"]["flagged"]
merged = json.load(open(out / "merged.json"))
c = next(c for c in merged["claims"] if c["id"] == "C01")
assert c["verdict"] == "Asserted" and [p["id"] for p in c["parts"]] == ["C01", "C04"], c
w = derive.claim_rows(merged)["C01"]["weakest"]
assert w["part"] == "C04" and "The weakest part is: Many threads can call the wallet module at the same time" in w["text"], w
print("a backup test keeps the proof Formal; a missed bug is a flag, not a lower part; a merged claim is as weak as its unproven part")
PY

step "bars: the surface of each claim, the frontend bar, the llm bar and the merge rule"
python3 "$S/onto.py" bars "$MAP" | tee "$O/bars.txt"
grep -q "^C01	backend	normal	Bar: property test or static rule · met" "$O/bars.txt"
grep -q "^C05	llm	normal	Bar: eval with a degraded control · below the bar: only a model judgment, no eval" "$O/bars.txt"
grep -q "^C04	other	" "$O/bars.txt"
B="$O/bars"; mkdir -p "$B/media"
python3 - "$MAP" "$B" <<'PY'
import json, pathlib, sys
data, out = json.load(open(sys.argv[1])), pathlib.Path(sys.argv[2])
tsx = json.loads(json.dumps(data))
next(c for c in tsx["claims"] if c["id"] == "C07")["code"] = [{"path": "web/Denial.tsx", "symbol": "Denial"}]
json.dump(tsx, open(out / "tsx.json", "w"), indent=2)
# A gate that filters model findings is deterministic code: backend, not llm. Words about model
# output with only code checks are unsure.
gate = json.loads(json.dumps(data))
c07 = next(c for c in gate["claims"] if c["id"] == "C07")
c07.update({"text": "The judge gate keeps each model finding that is not editable away from the editor.",
            "plain": {"what": "The judge reports findings. The gate sends the editor only the findings that it may fix.", "proof": "A unit test."},
            "code": [{"path": "src/judge/gate.py", "symbol": "fixable"}]})
c01 = next(c for c in gate["claims"] if c["id"] == "C01")
c01.update({"text": "Blind labellers agree that the new notes have fewer failures.", "plain": {"what": "The new notes are better.", "proof": "A test."}})
json.dump(gate, open(out / "gate.json", "w"), indent=2)
def variant(name, change):
    d = json.loads(json.dumps(data))
    change(d)
    (out / name).mkdir(exist_ok=True)
    json.dump(d, open(out / name / "trust-map.json", "w"), indent=2)
def frontend(video):
    def change(d):
        next(c for c in d["claims"] if c["id"] == "C07")["surface"] = "frontend"
        if video:
            v = next(v for v in d["verifiers"] if v["id"] == "V07")
            v["kind"] = "e2e"
            v["artifact"] = {"video": "media/denial-run.webm", "screenshots": ["media/denial-run.png"], "summary": "The page shows the amount in the denial."}
    return change
def llm(degraded, risky):
    def change(d):
        c = next(c for c in d["claims"] if c["id"] == "C05")
        c["risk"] = risky
        c["checks"].append("V40")
        ev = {"preregistered": True, "frozen": True, "blind": True, "k": 3}
        if degraded:
            ev["degraded"] = {"variant": "the prompt without the redaction rule", "score": 0.41, "baseline": 0.97}
        d["verifiers"].append({"id": "V40", "name": "the message eval", "kind": "eval", "claims": ["C05"], "tier": "fact", "eval": ev,
                               "description": "A frozen judge grades 40 denial messages for an account number.", "recorded": {"source": "eval run 7", "result": "0.97 clean"},
                               "independence": {"by": "tool", "tool": "eval harness"}, "cost": {"usd": 0}, "provenance": "A recorded eval run."})
    return change
variant("fe-unit", frontend(False)); variant("fe-video", frontend(True))
variant("llm-flagged", llm(False, True)); variant("llm-degraded", llm(True, False))
(out / "fe-video" / "media").mkdir(exist_ok=True)
(out / "fe-video" / "media" / "denial-run.webm").write_bytes(b"\x1aE\xdf\xa3 stub video")
(out / "fe-video" / "media" / "denial-run.png").write_bytes(bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"))
PY
python3 "$S/onto.py" bars "$B/tsx.json" | grep -q "^C07	frontend	normal	Bar: browser video · below the bar: only unit or component tests"
python3 "$S/onto.py" bars "$B/gate.json" > "$B/gate.txt"
grep -q "^C07	backend	" "$B/gate.txt" || { cat "$B/gate.txt"; echo "FAIL: a gate that filters model findings is not backend"; exit 1; }
grep -q "^C01	unsure (mixed)	" "$B/gate.txt" || { cat "$B/gate.txt"; echo "FAIL: words about model output with only code checks are not unsure"; exit 1; }
python3 "$S/onto.py" lint "$B/gate.json" | grep -q "^surface: 'the overdraft refusal' is unsure" || { echo "FAIL: no surface question for an unsure claim"; exit 1; }
echo "a gate that filters model findings is backend; words about model output with only code checks are unsure, and map asks"
for v in fe-unit fe-video llm-flagged llm-degraded; do
  python3 "$S/verdicts.py" "$B/$v/trust-map.json" > /dev/null
  cp "$FIX/explainer.mdx" "$B/$v/explainer.mdx"
  python3 "$S/explain.py" --map "$B/$v/trust-map.json" --repo "$REPO" --out "$B/$v" --extra "$FIX/explain.json" > "$B/$v/out.txt" 2>&1 || { cat "$B/$v/out.txt"; exit 1; }
done
python3 - "$B" <<'PY'
import html as h, json, pathlib, re, sys
b = pathlib.Path(sys.argv[1])
der = lambda v: json.loads((b / v / "refs.resolved.json").read_text())["derived"]  # noqa: E731
page = lambda v: (b / v / "explainer.html").read_text()  # noqa: E731
assert der("fe-unit")["claims"]["C07"]["bar"]["text"] == "Bar: browser video · below the bar: only unit or component tests", der("fe-unit")["claims"]["C07"]["bar"]
assert der("fe-video")["claims"]["C07"]["bar"]["met"], der("fe-video")["claims"]["C07"]["bar"]
root = page("fe-video").split('<div id="root">', 1)[1]
video = re.search(r"<video[^>]*>", root)
assert video and 'poster="media/denial-run.png"' in video.group(0) and "autoplay" not in video.group(0) and "controls" in video.group(0), video and video.group(0)
assert 'href="media/denial-run.webm"' in root, "no link to the video in the pre-render"
flag, deg = der("llm-flagged"), der("llm-degraded")
assert flag["claims"]["C05"]["bar"]["why"] == "the eval cannot show it can fail: no degraded variant ran", flag["claims"]["C05"]["bar"]
assert deg["claims"]["C05"]["bar"]["met"], deg["claims"]["C05"]["bar"]
assert flag["verify"]["evals"][0]["flagged"] and deg["verify"]["evals"][0]["text"] == "The real run scored 0.97. The degraded run (the prompt without the redaction rule) scored 0.41."
blocked = [i for i in flag["merge"]["items"] if i["href"] == "#claim-c05"]
assert blocked and blocked[0]["text"] == "Its eval has no degraded variant, so it cannot show that it can fail.", flag["merge"]["items"]
assert not [i for i in deg["merge"]["items"] if i["href"] == "#claim-c05"], "a claim at its bar is not a blocker"
text = h.unescape(re.sub(r"<[^>]+>", " ", page("llm-flagged").split('<div id="root">', 1)[1]))
assert "Bar: eval with a degraded control · below" in text and "Bar: property test or static rule · met" in text, "no bar chips"
assert re.search(r"\d+ of \d+ claims meet their bar", text), "no met counts"
assert "Degraded variants for evals" in text and "Flagged: no degraded run" in text and "Broken-UI runs" in text and "Planted bugs and mutants" in text, "the verify level lacks a kind of control"
assert 'data-ve-eval="degraded"' in page("llm-degraded"), "the degraded comparison is missing"
section = (b / "llm-flagged" / "pr-section.md").read_text()
assert "| Claim | Surface | Bar | Strength | Checks | Weakest check |" in section and "**Evidence bars:** " in section, section[:600]
print("the frontend bar needs a browser video (a video element with a poster in the pre-render); the llm bar needs a degraded variant; "
      "a risky claim below its bar blocks; the page has bar chips, met counts and the three kinds of control; the PR section has a Bar column")
PY

step "doctor: a doc that restates a bar"
D="$O/docs"; mkdir -p "$D/commands" "$D/references"
printf '# x\n\nThe frontend bar is a browser video of the real app.\n' > "$D/commands/x.md"
printf '# y\n\nThe bars are in [evidence-bars.md](../references/evidence-bars.md): a browser video for frontend.\n' > "$D/commands/y.md"
UNDERSTANDO_DOCS_ROOT="$D" "$U" --repo "$REPO" --run "$O/run" doctor --json > "$O/doctor-bars.json" || true
python3 - "$O/doctor-bars.json" <<'PY'
import json, sys
f = next((x for x in json.load(open(sys.argv[1]))["findings"] if x["id"] == "bar-restated"), None)
assert f and "commands/x.md:3" in f["summary"] and "commands/y.md" not in f["summary"], f
print("doctor flags the doc that restates a bar, and not the doc that links evidence-bars.md")
PY

echo
echo "PASS: the ontology e2e"
