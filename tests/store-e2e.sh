#!/usr/bin/env bash
# The store e2e: tests/e2e.sh calls it after the base run, with WORK, REPO, MAP, HEAD and FIX set.
# It drives the understando CLI in a fake HOME: the runs root, the run-state guard, publish to an
# orphan review branch on a local bare remote, publish --feedback, the read-only review cache,
# doctor on tracked run output, and the java lookup. No model call, no network.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$ROOT/tests/isolate.sh" store
U="$ROOT/bin/understando"
S="$ROOT/scripts"
T="$WORK/store"
step() { printf '\n== %s\n' "$*"; }
fail() { echo "FAIL: $*"; exit 1; }
has() { grep -qF -- "$2" "$1" || { echo "--- $1"; cat "$1"; fail "$1 lacks: $2"; }; }
lacks() { if grep -qF -- "$2" "$1"; then echo "--- $1"; cat "$1"; fail "$1 holds: $2"; fi; }
VE="${UNDERSTANDO_VE_RUNTIME:-}"
[ -n "$VE" ] || fail "no visual-explainer runtime: set ve_runtime with understando setup --ve-runtime PATH"
rm -rf "$T"; mkdir -p "$T"
export npm_config_cache="${npm_config_cache:-$HOME/.npm}"
FH="$T/home"; mkdir -p "$FH/.agents/skills"
# asd-ste100 is required (the prompt render and publish run its lint), so the fake HOME links the real one.
for d in "$HOME/.agents/skills/asd-ste100" "$HOME/.claude/skills/asd-ste100"; do
  [ -f "$d/SKILL.md" ] && { ln -s "$(readlink -f "$d")" "$FH/.agents/skills/asd-ste100"; break; }
done
[ -e "$FH/.agents/skills/asd-ste100" ] || fail "the required skill asd-ste100 is not installed"
export HOME="$FH" UNDERSTANDO_OFFLINE=1
# This test needs the default runs root, so it unsets the two. They are then in the fake HOME, in the test root.
unset UNDERSTANDO_HOME UNDERSTANDO_RUNS
isolate_selfcheck
gq() { git -C "$1" -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false "${@:2}"; }

# The reviewed repo: a clone of the fixture whose origin is a local bare repo named wallet.git.
git clone -q --bare "$REPO" "$T/wallet.git"
git -C "$T/wallet.git" config receive.denyNonFastForwards true
git -C "$T/wallet.git" config receive.denyDeletes true
git clone -q "$T/wallet.git" "$T/author"
A="$T/author"
git -C "$A" config user.name author; git -C "$A" config user.email author@example.invalid; git -C "$A" config commit.gpgsign false

step "runs root: with no override, a run folder resolves under ~/.understando/runs (the fake HOME)"
"$U" --repo "$A" --pr 7 note decision "the runs root test" > "$T/note.txt"
test -f "$FH/.understando/runs/wallet/7/journal.jsonl" || fail "no journal under $FH/.understando/runs/wallet/7"
test "$(python3 "$S/config.py" runs-root)" -ef "$FH/.understando/runs" || fail "runs-root is not ~/.understando/runs"
echo "the run folder is $FH/.understando/runs/wallet/7"

step "guard: a verb refuses to write run output inside the reviewed repo or any git repo"
if "$U" --run "$A/reviews/7" --repo "$A" note decision "x" > "$T/guard1.txt"; then fail "a note inside the reviewed repo passed"; fi
has "$T/guard1.txt" "is inside the reviewed repo"
test ! -e "$A/reviews" || fail "the refused note wrote into the reviewed repo"
if "$U" --run "$ROOT/runs/guard-test/1" note decision "x" > "$T/guard2.txt"; then fail "a note inside understando's checkout passed"; fi
has "$T/guard2.txt" "is inside the git repo"
mkdir -p "$FH/.understando/runs/wallet"
printf 'schema = "understando.repo/1"\nruns_dir = "%s"\n' "$A/runs" > "$FH/.understando/runs/wallet/understando.toml"
if "$U" --repo "$A" --pr 8 note decision "x" > "$T/guard3.txt"; then fail "runs_dir inside the reviewed repo passed"; fi
has "$T/guard3.txt" "is inside the reviewed repo"
rm "$FH/.understando/runs/wallet/understando.toml"
test -z "$(git -C "$A" status --porcelain)" || fail "the reviewed repo changed"
echo "the guard refuses the reviewed repo, understando's checkout and a runs_dir inside the repo"

step "publish: build the explainer through the CLI, then export it"
R="$T/run"; mkdir -p "$R"
cp "$MAP" "$R/trust-map.json"; cp "$FIX/explain.json" "$R/explain.json"; cp "$FIX/explainer.mdx" "$R/explainer.mdx"
"$U" --run "$R" --repo "$A" explain > "$T/explain1.txt"
test -f "$R/explain.stamp.json" || fail "explain wrote no stamp"
test -s "$R/explainer.html" || fail "explain exported no explainer.html"
printf '{"t": "planted"}\n' > "$R/journal.jsonl"; printf '{}\n' > "$R/discover.json"; printf '{}\n' > "$R/ci.json"
mkdir -p "$R/history" "$R/my-work"; printf '{}\n' > "$R/history/old.json"; printf 'x\n' > "$R/my-work/n.md"
printf 'export OPENAI_API_KEY=planted\n' > "$R/key-env.sh"
BR="understando/1-review"
STATUS0="$(git -C "$A" status --porcelain)"; HEAD0="$(git -C "$A" rev-parse HEAD)"; INDEX0="$(shasum "$A/.git/index")"

step "publish: no yes, no publish"
set +e; "$U" --run "$R" --repo "$A" publish 1 < /dev/null > "$T/pub-noyes.txt"; code=$?; set -e
test "$code" = 2 || { cat "$T/pub-noyes.txt"; fail "publish without a yes exited $code, not 2"; }
has "$T/pub-noyes.txt" "remote: origin ("; has "$T/pub-noyes.txt" "wallet.git)"; has "$T/pub-noyes.txt" "branch: $BR (a new orphan branch)"
has "$T/pub-noyes.txt" "    explainer.html"; has "$T/pub-noyes.txt" "    trust-map.json"; has "$T/pub-noyes.txt" "    README.md"
lacks "$T/pub-noyes.txt" "journal.jsonl"
echo '{"answer": "no"}' > "$T/no.json"
if "$U" --run "$R" --repo "$A" publish 1 --answers "$T/no.json" > "$T/pub-no.txt"; then fail "publish with a no passed"; fi
has "$T/pub-no.txt" "did not publish"
git -C "$T/wallet.git" rev-parse -q --verify "refs/heads/$BR" > /dev/null && fail "the branch exists without a yes"
git -C "$A" rev-parse -q --verify "refs/heads/$BR" > /dev/null && fail "a local branch exists without a yes"
echo "without a yes, publish prints the question and writes no branch"

step "publish: a yes makes an orphan branch with only the allowed files and no .github/"
echo '{"answer": "yes"}' > "$T/yes.json"
"$U" --run "$R" --repo "$A" publish 1 --answers "$T/yes.json" > "$T/pub1.txt"
has "$T/pub1.txt" "published "
TIP1="$(git -C "$T/wallet.git" rev-parse "refs/heads/$BR")"
test "$(git -C "$T/wallet.git" ls-tree -r --name-only "$TIP1" | tr '\n' ' ')" = "README.md explainer.html pr-section.md trust-map.json " \
  || fail "the tree holds: $(git -C "$T/wallet.git" ls-tree -r --name-only "$TIP1" | tr '\n' ' ')"
test "$(git -C "$T/wallet.git" rev-list --count "$TIP1")" = 1 || fail "the first review commit has a parent"
if git -C "$T/wallet.git" merge-base "$TIP1" main > /dev/null; then fail "the review branch shares history with main"; fi
git -C "$T/wallet.git" log -1 --format=%s "$TIP1" | grep -q "^Review of ${HEAD:0:8}: " || fail "the commit message: $(git -C "$T/wallet.git" log -1 --format=%s "$TIP1")"
test "$(git -C "$A" status --porcelain)" = "$STATUS0" || fail "publish changed the working tree"
test "$(git -C "$A" rev-parse HEAD)" = "$HEAD0" || fail "publish moved HEAD"
test "$(shasum "$A/.git/index")" = "$INDEX0" || fail "publish changed the index"
echo "orphan $BR at ${TIP1:0:10}: $(git -C "$T/wallet.git" log -1 --format=%s "$TIP1")"

step "fetch_review_branch: a read-only worktree in ~/.understando/review-cache"
rc() { python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import publish; print(publish.fetch_review_branch(sys.argv[2], sys.argv[3]))' "$S" "$@"; }
B="$T/reviewer"; git clone -q "$T/wallet.git" "$B"
git -C "$B" config user.name "Rita Reviewer"; git -C "$B" config user.email rita@example.invalid; git -C "$B" config commit.gpgsign false
DIR="$(rc "$B" 1)"
test "$DIR" -ef "$FH/.understando/review-cache/wallet/1" || fail "the cache folder is $DIR"
test -s "$DIR/explainer.html" || fail "no explainer.html in the cache"
test "$(git -C "$DIR" rev-parse HEAD)" = "$TIP1" || fail "the cache is not at the tip"
test ! -w "$DIR/explainer.html" || fail "the cached explainer is writable"
if (echo x >> "$DIR/explainer.html") 2>/dev/null; then fail "a write into the cache passed"; fi
echo "the cache at $DIR is read-only and at ${TIP1:0:10}"

step "publish --feedback: the reviewer's confusion rows go to feedback/<reviewer>.jsonl, after a yes"
RR="$T/rrun"; mkdir -p "$RR"
"$U" --run "$RR" --repo "$B" --pr 1 note confusion "I did not see why a fee can push the balance below zero" > /dev/null
"$U" --run "$RR" --repo "$B" --pr 1 note decision "not feedback" > /dev/null
set +e; "$U" --run "$RR" --repo "$B" --pr 1 publish --feedback < /dev/null > "$T/fb-noyes.txt"; code=$?; set -e
test "$code" = 2 || fail "feedback without a yes exited $code"
has "$T/fb-noyes.txt" "feedback/rita-reviewer.jsonl"
"$U" --run "$RR" --repo "$B" --pr 1 publish --feedback --answers "$T/yes.json" > "$T/fb.txt"
TIP2="$(git -C "$T/wallet.git" rev-parse "refs/heads/$BR")"
git -C "$T/wallet.git" merge-base --is-ancestor "$TIP1" "$TIP2" || fail "the feedback commit is not on top of the review"
git -C "$T/wallet.git" show "$TIP2:feedback/rita-reviewer.jsonl" > "$T/fb.jsonl"
has "$T/fb.jsonl" "below zero"; lacks "$T/fb.jsonl" "not feedback"
echo "feedback commit ${TIP2:0:10}: $(git -C "$T/wallet.git" log -1 --format=%s "$TIP2")"

step "publish: a stale explainer is refused (the HTML is older than the MDX, then the map changed)"
sleep 1
# The agent edits its narrative after the build.
printf '\n{/* A later edit of the narrative. */}\n' >> "$R/explainer.mdx"
if "$U" --run "$R" --repo "$A" publish 1 --answers "$T/yes.json" > "$T/stale1.txt"; then fail "publish took an HTML older than the MDX"; fi
has "$T/stale1.txt" "explainer.html is older than explainer.mdx"
"$U" --run "$R" --repo "$A" explain > /dev/null
cp "$R/trust-map.json" "$T/map.keep"
python3 - "$R/trust-map.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d.setdefault("notes", []).append("a later edit")
json.dump(d, open(sys.argv[1], "w"), indent=2)
PY
if "$U" --run "$R" --repo "$A" publish 1 --answers "$T/yes.json" > "$T/stale2.txt"; then fail "publish took a changed map"; fi
has "$T/stale2.txt" "trust-map.json changed after the explainer was built"
cp "$T/map.keep" "$R/trust-map.json"
test "$(git -C "$T/wallet.git" rev-parse "refs/heads/$BR")" = "$TIP2" || fail "a refused publish moved the branch"
echo "publish refuses an old HTML and a changed map"

step "publish: secret_paths refuses a published path"
mkdir -p "$FH/.understando/runs/wallet"
printf 'schema = "understando.repo/1"\nsecret_paths = ["**/.env*", "pr-section.md"]\n' > "$FH/.understando/runs/wallet/understando.toml"
if "$U" --run "$R" --repo "$A" publish 1 --answers "$T/yes.json" > "$T/secret.txt"; then fail "publish took a secret path"; fi
has "$T/secret.txt" "secret_paths: pr-section.md matches pr-section.md"
rm "$FH/.understando/runs/wallet/understando.toml"

step "publish: a second publish fetches the moved remote and adds a commit on top, with no force"
"$U" --run "$R" --repo "$A" publish 1 --answers "$T/yes.json" > "$T/pub2.txt"
has "$T/pub2.txt" "a new commit on top of ${TIP2:0:10}"
TIP3="$(git -C "$T/wallet.git" rev-parse "refs/heads/$BR")"
test "$(git -C "$T/wallet.git" rev-list --count "$TIP3")" = 3 || fail "want 3 commits on the branch"
test "$(git -C "$T/wallet.git" rev-parse "$TIP3^")" = "$TIP2" || fail "the second publish is not on top of the feedback commit"
git -C "$T/wallet.git" cat-file -e "$TIP3:feedback/rita-reviewer.jsonl" || fail "the second publish dropped the feedback"
if git -C "$T/wallet.git" ls-tree -r --name-only "$TIP3" | grep -q '^\.github/'; then fail "the tree holds .github/"; fi
"$U" --run "$R" --repo "$A" publish 1 --answers "$T/yes.json" > "$T/pub3.txt"
has "$T/pub3.txt" "nothing to push"
echo "commits on $BR: $(git -C "$T/wallet.git" rev-list --count "$TIP3"), each on top of the last"

step "fetch_review_branch: a second call updates the same read-only folder"
DIR2="$(rc "$B" 1)"
test "$DIR2" = "$DIR" || fail "the second call used $DIR2"
test "$(git -C "$DIR" rev-parse HEAD)" = "$TIP3" || fail "the cache did not move to the new tip"
test ! -w "$DIR/README.md" || fail "the updated cache is writable"
python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import publish; r = publish.feedback_rows(sys.argv[2], 1); assert len(r) == 1 and r[0]["reviewer"] == "rita-reviewer", r' "$S" "$A"
echo "the cache follows the branch; the author reads 1 feedback row"

step "doctor flags run output that the reviewed repo tracks, and a run folder in a git repo"
mkdir -p "$A/reviews/1"; cp "$MAP" "$A/reviews/1/trust-map.json"; echo '{}' > "$A/reviews/1/journal.jsonl"
gq "$A" add reviews && gq "$A" commit -q -m "track run output by mistake"
"$U" --run "$R" --repo "$A" --json doctor > "$T/doctor.json"
python3 - "$T/doctor.json" <<'PY'
import json, sys
f = {x["id"]: x for x in json.load(open(sys.argv[1]))["findings"]}
assert "run-output-tracked" in f and "reviews/1/trust-map.json" in f["run-output-tracked"]["summary"], f.keys()
assert "run-output-tracked-own" not in f, f["run-output-tracked-own"]
print("doctor:", f["run-output-tracked"]["summary"])
PY
"$U" --run "$A/reviews/1" --repo "$A" --json doctor > "$T/doctor2.json"
python3 -c 'import json,sys; f={x["id"] for x in json.load(open(sys.argv[1]))["findings"]}; assert "run-in-git" in f, f' "$T/doctor2.json"
echo "doctor flags a run folder inside the reviewed repo"

step "java: found from JAVA_HOME and from Homebrew's openjdk, with no java on PATH"
JH="$T/jdk"; mkdir -p "$JH/bin"
printf '#!/bin/sh\necho "openjdk version 21 (fake)" >&2\nexit 0\n' > "$JH/bin/java"; chmod +x "$JH/bin/java"
STRIP="$(dirname "$(command -v git)"):$(dirname "$(command -v python3)"):/usr/bin:/bin"
env -u UNDERSTANDO_JAVA PATH="$STRIP" JAVA_HOME="$JH" "$U" --run "$R" --json formalize > "$T/java1.json"
python3 -c 'import json,os,sys; j=json.load(open(sys.argv[1]))["toolchains"]["java"]; assert j and os.path.samefile(j, sys.argv[2]), j' "$T/java1.json" "$JH/bin/java"
if [ -x /opt/homebrew/opt/openjdk/bin/java ]; then
  env -u UNDERSTANDO_JAVA -u JAVA_HOME PATH="$STRIP" "$U" --run "$R" --json formalize > "$T/java2.json"
  python3 -c 'import json,sys; j=json.load(open(sys.argv[1]))["toolchains"]["java"]; assert j == "/opt/homebrew/opt/openjdk/bin/java", j' "$T/java2.json"
  echo "java: $JH/bin/java from JAVA_HOME, and /opt/homebrew/opt/openjdk/bin/java with no JAVA_HOME"
else
  echo "java: $JH/bin/java from JAVA_HOME (no Homebrew openjdk on this machine)"
fi

echo
echo "PASS: store e2e"
