#!/usr/bin/env bash
# Code refs end to end, on the fixture repo that tests/e2e.sh builds: symbol anchors, the snippet
# verb, permalinks, anchor controls, the no-hand-copy guard and the drift check in doctor.
#
#   WORK=... REPO=... MAP=... HEAD=... FIX=... bash tests/refs-e2e.sh    (tests/e2e.sh calls it)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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
extra["tradeoffs"].append("The guard is:\n" + "\n".join("  " + l.strip() for l in lines[start:start + 3]))
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
echo
echo "PASS: code refs"
