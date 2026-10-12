#!/usr/bin/env bash
# Code refs end to end, on the fixture repo that tests/e2e.sh builds: symbol anchors, the snippet
# verb, permalinks, anchor controls, the no-hand-copy guard, the drift check in doctor, and the
# refs of a check that runs on the review branch.
#
#   WORK=... REPO=... MAP=... HEAD=... FIX=... bash tests/refs-e2e.sh    (tests/e2e.sh calls it)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$ROOT/tests/isolate.sh" refs
S="$ROOT/scripts"
U=(python3 "$S/cli.py")
step() { printf '\n== %s\n' "$*"; }
g() { git -C "$1" -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false "${@:2}"; }
expect_fail() {  # expect_fail NAME WANT CMD...: the command must exit non-zero and print WANT
  local name="$1" want="$2"; shift 2
  if "$@" > "$WORK/$name.out" 2>&1; then echo "FAIL: $name passed"; cat "$WORK/$name.out"; exit 1; fi
  grep -q -- "$want" "$WORK/$name.out" || { echo "FAIL: $name failed for another reason:"; cat "$WORK/$name.out"; exit 1; }
}
code_of() { grep -E '^ *[0-9]+  ' | sed -E 's/^ *[0-9]+  //'; }

step "refs: a symbol ref resolves at the head"
"${U[@]}" --repo "$REPO" snippet wallet/core.py::withdraw --head "$HEAD" > "$WORK/snip-head.txt"
head -1 "$WORK/snip-head.txt" | grep -q "^wallet/core.py:8-15 at ${HEAD:0:10}" || { echo "FAIL: the symbol did not resolve to lines 8-15"; cat "$WORK/snip-head.txt"; exit 1; }
echo "wallet/core.py::withdraw resolves to lines 8-15"

step "refs: a commit moves the function down 10 lines; the anchor follows, the range drifts"
MOVED_REPO="$WORK/moved"
git clone -q "$REPO" "$MOVED_REPO"
python3 - "$MOVED_REPO/wallet/core.py" <<'PY'
import sys
p = sys.argv[1]
lines = open(p).read().splitlines(keepends=True)
i = next(n for n, l in enumerate(lines) if l.startswith("def withdraw"))
open(p, "w").write("".join(lines[:i] + [f"# A note line {n} that moves withdraw down.\n" for n in range(1, 10)] + ["\n"] + lines[i:]))
PY
g "$MOVED_REPO" commit -q -am "Move withdraw down 10 lines"
MOVED="$(g "$MOVED_REPO" rev-parse HEAD)"
"${U[@]}" --repo "$MOVED_REPO" snippet wallet/core.py::withdraw --head "$MOVED" > "$WORK/snip-moved.txt"
head -1 "$WORK/snip-moved.txt" | grep -q "^wallet/core.py:18-25 at ${MOVED:0:10}" || { echo "FAIL: the anchor did not follow the move"; cat "$WORK/snip-moved.txt"; exit 1; }
diff <(code_of < "$WORK/snip-head.txt") <(code_of < "$WORK/snip-moved.txt") > /dev/null || { echo "FAIL: the anchor shows other code after the move"; exit 1; }
"${U[@]}" --repo "$MOVED_REPO" snippet wallet/core.py --lines 8-15 --head "$MOVED" | code_of > "$WORK/range-moved.txt"
if diff -q <(code_of < "$WORK/snip-head.txt") "$WORK/range-moved.txt" > /dev/null; then echo "FAIL: the old range still shows withdraw"; exit 1; fi
echo "the anchor moves to lines 18-25 with the same code; the range 8-15 now shows other lines"

step "refs: a permalink has the head sha, from the git remote"
git -C "$MOVED_REPO" remote set-url origin https://github.com/example/wallet.git
"${U[@]}" --repo "$MOVED_REPO" snippet wallet/core.py::withdraw --head "$MOVED" | sed -n 2p > "$WORK/link.txt"
grep -qx "https://github.com/example/wallet/blob/$MOVED/wallet/core.py#L18-L25" "$WORK/link.txt" || { echo "FAIL: wrong permalink"; cat "$WORK/link.txt"; exit 1; }
grep -q "blob/$HEAD/wallet/core.py#L8-L15" "$WORK/explain/pr-section.md" || { echo "FAIL: the PR section has no permalink with the head sha"; exit 1; }
echo "permalink: $(cat "$WORK/link.txt")"

step "refs: an ambiguous anchor fails loudly in snippet, in explain and in probe"
expect_fail snip-ambiguous "it must occur once" "${U[@]}" --repo "$REPO" snippet wallet/core.py::withdraw --match "balance" --head "$HEAD"
expect_fail snip-missing "no such symbol" "${U[@]}" --repo "$REPO" snippet wallet/core.py::deposit --head "$HEAD"
python3 - "$MAP" "$WORK/ambiguous.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
next(c for c in data["claims"] if c["id"] == "C01")["code"] = [{"path": "wallet/core.py", "symbol": "withdraw", "match": "balance"}]
json.dump(data, open(sys.argv[2], "w"), indent=2)
PY
expect_fail explain-ambiguous "does not resolve at the head" python3 "$S/explain.py" --map "$WORK/ambiguous.json" --repo "$REPO" --out "$WORK/bad-ambiguous" --extra "$FIX/explain.json"
echo "snippet and explain refuse an anchor that matches 0 places or more than 1"

step "refs: anchor controls go red, and an ambiguous control is an ANCHOR ERROR"
python3 - "$MAP" "$WORK/anchor-controls.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
k01 = next(k for k in data["controls"] if k["id"] == "K01")
assert k01["edits"][0]["op"] == "replace-with" and k01["result"]["status"] == "red", k01
data["controls"] += [
    {"id": "K90", "verifier": "V01", "recipe": "invert-condition", "description": "Invert the overdraft guard.",
     "edits": [{"op": "invert-condition", "path": "wallet/core.py", "symbol": "withdraw", "match": "amount > balance"}],
     "expect": {"status": "red"}},
    {"id": "K91", "verifier": "V01", "recipe": "remove-guard-line", "description": "Delete the overdraft guard.",
     "edits": [{"op": "delete-line", "path": "wallet/core.py", "symbol": "withdraw", "match": "if amount > balance:"}],
     "expect": {"status": "red"}},
    {"id": "K92", "verifier": "V01", "recipe": "remove-guard-line", "description": "An anchor that matches twice.",
     "edits": [{"op": "delete-line", "path": "wallet/core.py", "symbol": "withdraw", "match": "balance"}],
     "expect": {"status": "red"}},
]
json.dump(data, open(sys.argv[2], "w"), indent=2)
PY
for k in K90 K91; do python3 "$S/run_control.py" --map "$WORK/anchor-controls.json" --repo "$REPO" --control "$k" --scratch "$WORK/scratch"; done
expect_fail control-ambiguous "ANCHOR ERROR: control K92" python3 "$S/run_control.py" --map "$WORK/anchor-controls.json" --repo "$REPO" --control K92 --scratch "$WORK/scratch"
python3 - "$WORK/anchor-controls.json" <<'PY'
import json, sys
ks = {k["id"]: k for k in json.load(open(sys.argv[1]))["controls"]}
for kid, want in (("K01", "+        pass"), ("K90", "+    if amount <= balance:"), ("K91", "-    if amount > balance:")):
    r = ks[kid]["result"]
    if r["status"] != "red" or want not in r.get("diff", ""):
        sys.exit(f"FAIL: {kid} is {r['status']}, diff {r.get('diff')!r}")
    print(f"{kid} ({ks[kid]['edits'][0]['op']}) went red; its diff holds {want.strip()!r}")
if ks["K92"]["result"]["status"] != "error":
    sys.exit("FAIL: K92 did not record an error")
PY

step "refs: the no-hand-copy guard fails a build with a pasted 3-line block"
python3 - "$FIX/explain.json" "$WORK/pasted.json" "$REPO/wallet/core.py" <<'PY'
import json, sys
extra = json.load(open(sys.argv[1]))
lines = open(sys.argv[3]).read().splitlines()
start = next(i for i, l in enumerate(lines) if "if amount > balance" in l)
# A model types the block again, with its own indentation: the guard normalises whitespace.
extra["risks"][0]["why"] += "\nThe guard is:\n" + "\n".join("  " + l.strip() for l in lines[start:start + 3])
json.dump(extra, open(sys.argv[2], "w"), indent=2)
PY
expect_fail pasted "pasted code from wallet/core.py:13" python3 "$S/explain.py" --map "$MAP" --repo "$REPO" --out "$WORK/bad-pasted" --extra "$WORK/pasted.json"
grep -m1 "pasted code" "$WORK/pasted.out"

step "refs: doctor reports pasted code, and an anchor that drifts on a newer head, as a route to map"
mkdir -p "$WORK/drift-run"
cp "$MAP" "$WORK/drift-run/trust-map.json"
cp "$WORK/pasted.json" "$WORK/drift-run/explain.json"
sed -i.bak 's/def withdraw(/def take(/' "$MOVED_REPO/wallet/core.py" && rm "$MOVED_REPO/wallet/core.py.bak"
g "$MOVED_REPO" commit -q -am "Rename withdraw to take"
RENAMED="$(g "$MOVED_REPO" rev-parse HEAD)"
"${U[@]}" --repo "$MOVED_REPO" --run "$WORK/drift-run" --json doctor --pr-head "$RENAMED" > "$WORK/doctor-refs.json"
python3 - "$WORK/doctor-refs.json" "$RENAMED" <<'PY'
import json, sys
found = {f["id"]: f for f in json.load(open(sys.argv[1]))["findings"]}
drift = found.get("anchor-drift-" + sys.argv[2][:10])
paste = found.get("pasted-code")
if not drift or drift["severity"] != "route" or drift.get("verb") != "map" or "no such symbol" not in drift["summary"]:
    sys.exit(f"FAIL: no anchor-drift route to map: {sorted(found)}")
if not paste or paste["severity"] != "route" or paste.get("verb") != "map":
    sys.exit(f"FAIL: no pasted-code route to map: {sorted(found)}")
if any(k.startswith("anchor-drift") and k != "anchor-drift-" + sys.argv[2][:10] for k in found):
    sys.exit("FAIL: an anchor drifts at the map head")
print("doctor: " + drift["summary"][:110] + " ...")
print("doctor: " + paste["summary"][:110] + " ...")
PY
step "refs: a check that runs on the review branch resolves at the ready head; the PR's own code keeps the PR head"
# The review branch adds a test that the PR head does not have. Its check has `at` (reverify_map
# sets it); a CodeRef of the MDX names the same file, absent at the PR head.
READY_REPO="$WORK/ready-repo"
git clone -q "$REPO" "$READY_REPO"
git -C "$READY_REPO" remote set-url origin https://github.com/example/wallet.git
g "$READY_REPO" checkout -q -b understando/7-ready
cat > "$READY_REPO/tests/test_ready_only.py" <<'PYT'
import unittest

from wallet.core import withdraw


class ReadyOnlyTest(unittest.TestCase):
    def test_an_overdraft_is_refused_on_the_review_branch(self):
        with self.assertRaises(ValueError):
            withdraw(5, 10)
PYT
g "$READY_REPO" add -A
g "$READY_REPO" commit -q -m "A check that the review adds"
READY="$(g "$READY_REPO" rev-parse HEAD)"
mkdir -p "$WORK/ready-run"
cp "$WORK/examples.json" "$WORK/ready-run/examples.json"
python3 - "$MAP" "$WORK/ready-run/trust-map.json" "$READY" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
data["ready"] = {"branch": "understando/7-ready", "head": sys.argv[3]}
v = next(v for v in data["verifiers"] if v["id"] == "V07")
v["at"] = sys.argv[3]
v["command"]["argv"] = ["python3", "-m", "pytest", "-q", "tests/test_ready_only.py::ReadyOnlyTest::test_an_overdraft_is_refused_on_the_review_branch"]
json.dump(data, open(sys.argv[2], "w"), indent=2)
PY
sed 's|<CodeRef refs={refs} path="wallet/core.py" symbol="withdraw" />|&\
\
<CodeRef refs={refs} path="tests/test_ready_only.py" symbol="ReadyOnlyTest" />|' "$FIX/explainer.mdx" > "$WORK/ready-run/explainer.mdx"
grep -q 'path="tests/test_ready_only.py"' "$WORK/ready-run/explainer.mdx" || { echo "FAIL: the fixture MDX has no CodeRef for the ready-only file"; exit 1; }
python3 "$S/explain.py" --map "$WORK/ready-run/trust-map.json" --repo "$READY_REPO" --out "$WORK/ready-run" --extra "$FIX/explain.json" > "$WORK/ready-explain.out" 2>&1 \
  || { echo "FAIL: explain did not build with a check on the review branch"; tail -20 "$WORK/ready-explain.out"; exit 1; }
if grep -q "does not resolve" "$WORK/ready-explain.out"; then echo "FAIL: explain reports a ref that does not resolve"; cat "$WORK/ready-explain.out"; exit 1; fi
python3 - "$WORK/ready-run" "$HEAD" "$READY" <<'PY'
import html as h, json, re, sys
from pathlib import Path
run, head, ready = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
refs = json.loads((run / "refs.resolved.json").read_text())
by = {(r["ref"]["path"], r["ref"].get("symbol")): r for r in refs["refs"]}
check = by.get(("tests/test_ready_only.py", "ReadyOnlyTest.test_an_overdraft_is_refused_on_the_review_branch"))
cls = by.get(("tests/test_ready_only.py", "ReadyOnlyTest"))
pr = by.get(("wallet/core.py", "withdraw"))
for name, r, sha in (("the check test", check, ready), ("the CodeRef on the review branch", cls, ready), ("the PR-head ref", pr, head)):
    if not r:
        sys.exit(f"FAIL: {name} is not in refs.resolved.json")
    if r["commit"] != sha:
        sys.exit(f"FAIL: {name} resolved at {r['commit'][:10]}, not {sha[:10]}")
    if f"/blob/{sha}/{r['ref']['path']}#L{r['start']}" not in (r["permalink"] or ""):
        sys.exit(f"FAIL: the permalink of {name} is {r['permalink']}")
    if bool(r.get("on_review_branch")) != (sha == ready):
        sys.exit(f"FAIL: {name} is marked on_review_branch={r.get('on_review_branch')}")
if check["start"] != 7 or check["end"] != 9 or "withdraw(5, 10)" not in check["excerpt"]:
    sys.exit(f"FAIL: the check test resolved to lines {check['start']}-{check['end']}")
if refs["derived"]["checks"]["V07"]["ref"] != check["ref"]:
    sys.exit("FAIL: the V07 check row does not name its test")
# The page: the code of the review branch is marked in its code block; the PR code is not.
page = re.sub(r"<script\b.*?</script>", "", (run / "explainer.html").read_text(), flags=re.S)
names = [h.unescape(re.sub(r"<[^>]+>", "", m)) for m in re.findall(r'class="ve-code-name">(.*?)</span></figcaption>', page, flags=re.S)]
if not any(n.startswith("On the review branch, tests/test_ready_only.py:") for n in names):
    sys.exit(f"FAIL: the page does not mark the review-branch code: {names}")
if not any(n.startswith("wallet/core.py:") for n in names):
    sys.exit(f"FAIL: the page does not show the PR code at the PR head: {names}")
print(f"the check test and the CodeRef resolve at the ready head {ready[:10]}, the PR code at {head[:10]}; the page shows: "
      + next(n for n in names if n.startswith("On the review branch")))
PY
"${U[@]}" --repo "$READY_REPO" --run "$WORK/ready-run" snippet tests/test_ready_only.py::ReadyOnlyTest | head -1 | grep -q "at ${READY:0:10} (on the review branch)" \
  || { echo "FAIL: snippet does not resolve the ready-only file at the ready head"; exit 1; }
echo "snippet: tests/test_ready_only.py::ReadyOnlyTest resolves at the ready head"

step "refs: a .lean theorem anchor and a .tla definition anchor resolve in a fixture"
FX="$WORK/formal-fx"
mkdir -p "$FX"
cat > "$FX/Model.lean" <<'LEAN'
namespace Fx

def settle (xs : List Nat) : Option Nat :=
  match xs with
  | [] => none
  | x :: _ => some x

theorem settle_nil : settle [] = none := by
  rfl

theorem settle_cons (x : Nat) (xs : List Nat) :
    settle (x :: xs) = some x := by
  rfl

end Fx
LEAN
cat > "$FX/Spec.tla" <<'TLA'
---- MODULE Spec ----
EXTENDS Naturals
VARIABLES n
Init == n = 0

Step(k) == /\ n < 3
           /\ n' = n + k

Next == Step(1)
====
TLA
git -C "$FX" init -q
g "$FX" add -A
g "$FX" commit -q -m "A Lean model and a TLA+ spec"
snip() { "${U[@]}" --repo "$FX" snippet "$@" | head -1 | sed -E 's/ at [0-9a-f]+.*//'; }
[ "$(snip Model.lean::settle_cons)" = "Model.lean:11-13" ] || { echo "FAIL: the lean theorem did not resolve to lines 11-13"; snip Model.lean::settle_cons; exit 1; }
[ "$(snip Model.lean::settle)" = "Model.lean:3-6" ] || { echo "FAIL: the lean def did not resolve to lines 3-6"; snip Model.lean::settle; exit 1; }
[ "$(snip Spec.tla::Step)" = "Spec.tla:6-7" ] || { echo "FAIL: the tla definition did not resolve to lines 6-7"; snip Spec.tla::Step; exit 1; }
"${U[@]}" --repo "$FX" snippet Spec.tla::Step --match "n' = n + k" | code_of | grep -Fqx "           /\\ n' = n + k" || { echo "FAIL: the tla match did not resolve"; exit 1; }
expect_fail lean-missing "no such symbol" "${U[@]}" --repo "$FX" snippet Model.lean::settle_none
expect_fail tla-missing "no such symbol" "${U[@]}" --repo "$FX" snippet Spec.tla::Stop
echo "Model.lean::settle_cons is lines 11-13, Model.lean::settle is 3-6, Spec.tla::Step is 6-7"

step "refs: formal_tlc control by anchor plants the spec, and a bad anchor is an ANCHOR ERROR"
TLA="$ROOT/tests/formal/repo/formal/tla"
S="$S" python3 - "$TLA/Retry.tla" "$WORK/Retry.planted.tla" <<'PY'
import os
import sys
sys.path.insert(0, os.environ["S"])
import coderef
src = open(sys.argv[1]).read()
edit = coderef.cli_edit("Retry.tla", None, "Call", '/== (\\/\\\\ result = "running")/', "TRUE")
assert edit["op"] == "replace-with", edit
open(sys.argv[2], "w").write(coderef.apply_text(src, edit))
PY
diff <(cat "$TLA/Retry.tla") "$WORK/Retry.planted.tla" > "$WORK/retry.diff" || true
grep -qx '< Call(o) == /\\ result = "running"' "$WORK/retry.diff" && grep -qx '> Call(o) == TRUE' "$WORK/retry.diff" && [ "$(grep -c '^[<>]' "$WORK/retry.diff")" = 2 ] || { echo "FAIL: the anchor planted another spec"; cat "$WORK/retry.diff"; exit 1; }
python3 "$S/formal_tlc.py" control --spec "$TLA/Retry.tla" --cfg "$TLA/Retry.cfg" \
  --symbol Call --match '/== (\/\\ result = "running")/' --with TRUE --pattern NoCallAfterStop > "$WORK/tlc-anchor.json"
python3 - "$WORK/tlc-anchor.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
want = {"op": "replace-with", "path": "Retry.tla", "symbol": "Call", "match": '/== (\\/\\\\ result = "running")/', "with": "TRUE"}
if r["status"] != "red" or r["control"]["edit"] != want or r["control"]["matched"] is not True or "find" in r["control"]:
    sys.exit(f"FAIL: the anchor control is {r['status']}: {r['control']}")
print("formal_tlc control by anchor: TLC went red on NoCallAfterStop; the record holds the anchor edit, no typed find")
PY
expect_fail tlc-anchor-missing "ANCHOR ERROR" python3 "$S/formal_tlc.py" control --spec "$TLA/Retry.tla" --cfg "$TLA/Retry.cfg" --symbol NoSuchDefinition --match x --with y
expect_fail tlc-find-deprecated "deprecated" python3 "$S/formal_tlc.py" control --spec "$TLA/Retry.tla" --cfg "$TLA/Retry.cfg" --find 'no such text' --replace x

step "refs: discover finds an anchor control as existing, by its resolved location"
mkdir -p "$WORK/disc-run"
cp "$WORK/anchor-controls.json" "$WORK/disc-run/trust-map.json"
"${U[@]}" --repo "$REPO" --run "$WORK/disc-run" discover > "$WORK/discover-anchor.txt"
python3 - "$WORK/disc-run/discover.json" <<'PY'
import json, sys
cands = json.load(open(sys.argv[1]))["candidates"]
hit = [c for c in cands if c.get("path") == "wallet/core.py" and any(e.startswith("control K9") for e in c["evidence"])]
if not hit:
    sys.exit("FAIL: discover missed the anchor controls: " + json.dumps([(c.get("path"), c.get("function"), c["evidence"]) for c in cands]))
found = sorted({e for c in hit for e in c["evidence"] if e.startswith("control ")})
if "control K90" not in found or "control K91" not in found:
    sys.exit(f"FAIL: discover found only {found}")
print("discover: wallet/core.py candidates already have", ", ".join(found))
PY
echo
echo "PASS: code refs"
