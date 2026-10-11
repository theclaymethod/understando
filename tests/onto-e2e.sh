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
grep -q "Its changed symbols: denial" "$O/draft.out"
grep -q "Checks that run it: the denial amount test" "$O/draft.out"
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
echo
echo "PASS: the ontology e2e"
