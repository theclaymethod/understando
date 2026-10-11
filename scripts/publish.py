"""understando publish: share a review on an orphan branch of the reviewed repo.

    understando publish [<pr>] [--answers FILE] [--dry-run]
    understando publish [<pr>] --feedback [--reviewer NAME] [--answers FILE] [--dry-run]

The user starts it. It is outward-facing, so it always asks for a clear yes first, and the question
names the exact remote, branch and file list. The answer file is JSON: {"answer": "yes"}. Without a
terminal and without an answer file, it prints the question and publishes nothing (exit 2).

publish builds or updates the orphan branch understando/<pr>-review in the reviewed repo. The branch
holds only explainer.html (and the local assets it links), trust-map.json, pr-section.md and a
README.md that tells how to open it. It never holds journal.jsonl, discover.json, history/, ci.json,
review.json, my-work/ or a key file, and it never holds a .github/ folder, so no CI runs on it. It
uses git plumbing (hash-object, a temporary index, write-tree, commit-tree, update-ref), so the
working tree, the index and HEAD of the reviewed repo do not change. Each update is a normal commit
on top of the remote tip; feedback/ files on the branch stay. It never force-pushes.

It refuses when the explainer is stale (explain.stamp.json does not match the map head, the
trust-map hash, explainer.mdx and pr-section.md, or explainer.html is older than explainer.mdx),
when the no-hand-copy guard finds pasted code, when a published path or a code ref matches
secret_paths or a file holds a key-like string, or when the tree would hold .github/.

publish --feedback (a reviewer): append the reviewer's own `kind: confusion` journal rows to
feedback/<reviewer>.jsonl on the review branch, after a yes. feedback_rows() reads them back for the
author's review.

fetch_review_branch(repo, pr) -> Path: the read-only checkout that `understando open <pr>` uses.
Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tm  # noqa: E402

STAMP = "explain.stamp.json"
STAMP_SCHEMA = "understando.explain-stamp/1"
FILES = ("explainer.html", "trust-map.json", "pr-section.md")
NEVER = ("journal.jsonl", "discover.json", "history", "ci.json", "review.json", "my-work", "decisions.tsv",
         "key-env.sh", "refs.resolved.json", ".lock", ".lock.mutex")
KEY_FILE = re.compile(r"(^|/)(\.env[^/]*|[^/]*\.(pem|key|p12|pfx)|id_(rsa|ed25519|ecdsa)[^/]*|key-env\.sh)$")
YES = {"yes", "y"}


class PublishError(RuntimeError):
    """A refusal or a git failure. The message is for the user."""


def branch_name(pr: str | int) -> str:
    return f"understando/{pr}-review"


def _git(repo: Path, *args: str, env: dict | None = None, input_: str | None = None, check: bool = True) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, input=input_,
                         env={**os.environ, **(env or {})})
    if check and out.returncode != 0:
        raise PublishError(f"git {' '.join(args[:3])} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def _sha256(path: Path) -> str | None:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


# ---- the explainer stamp -----------------------------------------------------------------------

def write_stamp(run: Path, map_sha: str) -> Path:
    """Record what explain built from. `understando explain` calls it after a good build, with the
    trust-map hash taken before the build."""
    data = tm.load(run / "trust-map.json")
    stamp = {"schema": STAMP_SCHEMA, "map_head": data["head"], "trust_map_sha256": map_sha,
             "explainer_mdx_sha256": _sha256(run / "explainer.mdx"), "pr_section_sha256": _sha256(run / "pr-section.md"),
             "written": tm.now()}
    p = run / STAMP
    p.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    return p


def stale_reasons(run: Path, data: dict) -> list[str]:
    p = run / STAMP
    if not p.is_file():
        return [f"no {STAMP}: build the explainer with `understando explain`, then export explainer.html"]
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [f"{p} is not valid JSON: build the explainer again"]
    out = []
    if s.get("map_head") != data.get("head"):
        out.append(f"the explainer is for head {str(s.get('map_head'))[:10]}, the map is at {data['head'][:10]}")
    if s.get("trust_map_sha256") != _sha256(run / "trust-map.json"):
        out.append("trust-map.json changed after the explainer was built")
    if s.get("explainer_mdx_sha256") != _sha256(run / "explainer.mdx"):
        out.append("explainer.mdx differs from the one that explain built")
    if s.get("pr_section_sha256") != _sha256(run / "pr-section.md"):
        out.append("pr-section.md differs from the one that explain built")
    html, mdx = run / "explainer.html", run / "explainer.mdx"
    if not html.is_file():
        out.append("there is no explainer.html: export it (commands/explain.md, step 5)")
    elif mdx.is_file() and html.stat().st_mtime < mdx.stat().st_mtime:
        out.append("explainer.html is older than explainer.mdx: export it again")
    return out


# ---- the file plan -----------------------------------------------------------------------------

def _assets(run: Path) -> list[str]:
    """The local files that explainer.html links: relative src/href values that resolve to a file
    inside the run folder, and an assets/ folder when it exists."""
    html = (run / "explainer.html").read_text(encoding="utf-8", errors="ignore")
    found = set()
    for m in re.finditer(r"""(?:src|href)\s*=\s*["']([^"'#?]+)""", html):
        v = m.group(1)
        if re.match(r"^[a-z][a-z0-9+.-]*:", v, re.I) or v.startswith(("/", "//")):
            continue
        p = (run / v).resolve()
        if run.resolve() in p.parents and p.is_file():
            found.add(p.relative_to(run.resolve()).as_posix())
    if (run / "assets").is_dir():
        found |= {p.relative_to(run).as_posix() for p in (run / "assets").rglob("*") if p.is_file()}
    return sorted(found)


def readme(data: dict, pr: str, branch: str) -> str:
    s = data.get("summary") or {}
    return "\n".join([
        f"# Review of PR #{pr}: {data.get('title') or data.get('repo')}", "",
        f"understando wrote this branch for the PR head `{data['head'][:10]}` ({', '.join(f'{k} {v}' for k, v in s.items())}).",
        "It is an orphan branch: it shares no history with the code, and it has no `.github/` folder, so no CI runs on it.", "",
        "## Open it", "",
        "```bash",
        f"git fetch origin {branch} && git worktree add /tmp/review-{pr} FETCH_HEAD && open /tmp/review-{pr}/explainer.html",
        "```", "",
        f"With understando: `understando open {pr}`.", "",
        "## Files", "",
        "- `explainer.html`: the explainer page, one self-contained file.",
        "- `trust-map.json`: the claims, the verifiers, the controls and the verdicts.",
        "- `pr-section.md`: the PR-body section.",
        "- `feedback/<reviewer>.jsonl`: the points that confused a reviewer (`understando publish --feedback`).", ""])


def message(data: dict) -> str:
    s = data.get("summary") or {}
    return f"Review of {data['head'][:8]}: " + ", ".join(f"{k} {v}" for k, v in s.items())


def checks(run: Path, repo: Path, data: dict, cfg: dict, files: dict[str, bytes]) -> list[str]:
    """Every refusal for a publish of `files` (path -> bytes). An empty list is the good result."""
    import coderef
    import config
    import journal
    out = [f"stale explainer: {r}" for r in stale_reasons(run, data)]
    extra = tm.load(run / "explain.json") if (run / "explain.json").is_file() else {}
    pasted = coderef.pasted(repo, data["head"], coderef.guard_inputs(data, extra, [tm.ROOT / "templates" / "three-level.mdx"]))
    out += [f"no-hand-copy guard: {p}" for p in pasted[:5]]
    for rel, blob in files.items():
        top = rel.split("/", 1)[0]
        if top == ".github":
            out.append(f".github check: the tree would hold {rel}; a review branch must never start CI")
        if top in NEVER or rel in NEVER or KEY_FILE.search(rel):
            out.append(f"never published: {rel}")
        g = config.secret(cfg, rel)
        if g:
            out.append(f"secret_paths: {rel} matches {g}")
        text = blob.decode("utf-8", errors="ignore")
        for pat in journal.KEY_PATTERNS:
            m = pat.search(text)
            if m:
                out.append(f"secret scan: {rel} holds a key-like string at offset {m.start()}")
                break
    for where, rel in _code_paths(data):
        g = config.secret(cfg, rel)
        if g:
            out.append(f"secret_paths: trust-map.json {where} cites {rel}, which matches {g}")
    return out


def _code_paths(value, where: str = "$"):
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ("path", "artifact") and isinstance(v, str):
                yield where, v
            else:
                yield from _code_paths(v, f"{where}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _code_paths(v, f"{where}[{i}]")


# ---- the branch --------------------------------------------------------------------------------

def remote_tip(repo: Path, branch: str, fetch: bool) -> str | None:
    """The tip of origin's branch. With fetch, ask origin and update origin/<branch>; else read the
    remote-tracking ref only."""
    if fetch:
        out = _git(repo, "ls-remote", "--heads", "origin", f"refs/heads/{branch}")
        if not out:
            return None
        _git(repo, "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}")
    return _git(repo, "rev-parse", "-q", "--verify", f"refs/remotes/origin/{branch}^{{commit}}", check=False) or None


def tree_entries(repo: Path, commit: str | None) -> dict[str, tuple[str, str]]:
    """path -> (mode, blob sha) of a commit's tree."""
    if not commit:
        return {}
    out = {}
    for line in _git(repo, "ls-tree", "-r", "-z", "--full-tree", commit).split("\0"):
        if line:
            meta, path = line.split("\t", 1)
            mode, _, sha = meta.split()
            out[path] = (mode, sha)
    return out


def build_commit(repo: Path, entries: dict[str, tuple[str, str]], blobs: dict[str, bytes], parent: str | None, msg: str) -> tuple[str, str]:
    """Write the blobs, build the tree in a temporary index, and make the commit. (commit, tree)."""
    with tempfile.TemporaryDirectory(prefix="understando-publish-") as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        merged = dict(entries)
        for rel, blob in blobs.items():
            f = Path(tmp) / "blob"
            f.write_bytes(blob)
            merged[rel] = ("100644", _git(repo, "hash-object", "-w", str(f)))
        _git(repo, "read-tree", "--empty", env=env)
        info = "".join(f"{mode} {sha}\t{path}\n" for path, (mode, sha) in sorted(merged.items()))
        _git(repo, "update-index", "--index-info", env=env, input_=info)
        tree = _git(repo, "write-tree", env=env)
    paths = _git(repo, "ls-tree", "-r", "--name-only", tree).splitlines()
    if any(p == ".github" or p.startswith(".github/") for p in paths):
        raise PublishError("refuse: the review tree holds .github/; a review branch must never start CI")
    if parent and _git(repo, "rev-parse", f"{parent}^{{tree}}") == tree:
        return parent, tree
    commit = _git(repo, "commit-tree", tree, *(["-p", parent] if parent else []), "-m", msg)
    return commit, tree


def push(repo: Path, branch: str, commit: str) -> None:
    """Point the local refs/heads/<branch> at `commit`, then push it. Never a force push: origin
    accepts it only when `commit` descends from origin's tip."""
    _git(repo, "update-ref", "-m", "understando publish", f"refs/heads/{branch}", commit)
    _git(repo, "push", "-q", "origin", branch)


# ---- asking ------------------------------------------------------------------------------------

def question(repo: Path, branch: str, files: list[str], kept: list[str], parent: str | None, msg: str) -> str:
    url = _git(repo, "remote", "get-url", "origin", check=False) or "(no origin)"
    lines = ["Publish this review? understando writes one commit and pushes it:",
             "  remote: origin (" + url + ")",
             f"  branch: {branch} " + (f"(a new commit on top of {parent[:10]})" if parent else "(a new orphan branch)"),
             f"  commit: {msg}",
             "  files:"]
    lines += [f"    {f}" for f in files]
    if kept:
        lines += ["  kept from the branch:"] + [f"    {f}" for f in kept]
    lines += [f"  push: git push origin {branch} (never a force push)",
              "Answer yes to publish. Any other answer publishes nothing."]
    return "\n".join(lines)


def answer(path: str | None) -> str | None:
    if path:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PublishError(f"refuse: the answer file {path} is not readable JSON: {exc}")
        return str(raw.get("answer", "")).strip().lower() if isinstance(raw, dict) else ""
    if sys.stdin.isatty():
        return input("Publish? [yes/N] ").strip().lower()
    return None


# ---- the verbs ---------------------------------------------------------------------------------

def publish_review(c, answers: str | None, dry_run: bool) -> int:
    import config
    run, repo = c.need_run(), c.need_repo()
    data = c.need_map()
    pr = str(c.pr or data.get("pr"))
    branch = branch_name(pr)
    cfg = config.for_repo(repo)
    blobs = {name: (run / name).read_bytes() for name in FILES if (run / name).is_file()}
    if (run / "explainer.html").is_file():
        blobs.update({a: (run / a).read_bytes() for a in _assets(run)})
    blobs["README.md"] = readme(data, pr, branch).encode("utf-8")
    refusals = checks(run, repo, data, cfg, blobs)
    refusals += [f"missing: {n}" for n in FILES if n not in blobs and not any(n in r for r in refusals)]
    parent = remote_tip(repo, branch, fetch=not dry_run)
    if not parent:
        parent = _git(repo, "rev-parse", "-q", "--verify", f"refs/heads/{branch}^{{commit}}", check=False) or None
    kept = sorted(p for p in tree_entries(repo, parent) if p.startswith("feedback/"))
    msg = message(data)
    q = question(repo, branch, sorted(blobs), kept, parent, msg)
    if refusals:
        print(("dry run: " if dry_run else "") + "publish refuses:\n  " + "\n  ".join(refusals))
        if dry_run:
            print("\n" + q + "\n\ndry run: nothing written, nothing fetched or pushed; the branch tip comes from local refs.")
        return 1
    print(q)
    if dry_run:
        print("\ndry run: nothing written, nothing fetched or pushed; the branch tip comes from local refs.")
        return 0
    got = answer(answers)
    if got is None:
        print("\npublish: no terminal and no --answers FILE. Ask the user the question above; on a yes, pass {\"answer\": \"yes\"}.")
        return 2
    if got not in YES:
        print("publish: the answer is not yes; nothing is published.")
        return 1
    entries = {p: v for p, v in tree_entries(repo, parent).items() if p.startswith("feedback/")}
    commit, _ = build_commit(repo, entries, blobs, parent, msg)
    if commit == parent:
        print(f"publish: {branch} already holds these files at {parent[:10]}; nothing to push.")
        return 0
    try:
        push(repo, branch, commit)
    except PublishError as exc:
        # The remote moved while we built: fetch, commit on top of the new tip, and try once more.
        new_parent = remote_tip(repo, branch, fetch=True)
        if not new_parent or new_parent == parent:
            raise PublishError(f"refuse: the push failed and origin did not move: {exc}")
        entries = {p: v for p, v in tree_entries(repo, new_parent).items() if p.startswith("feedback/")}
        commit, _ = build_commit(repo, entries, blobs, new_parent, msg)
        push(repo, branch, commit)
    print(f"published {commit[:10]} to origin {branch}")
    return 0


def reviewer_name(explicit: str | None, repo: Path) -> str:
    raw = explicit or _git(repo, "config", "user.name", check=False) or os.environ.get("USER", "reviewer")
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", raw.strip()).strip("-.").lower()
    if not name:
        raise PublishError("refuse: no reviewer name; pass --reviewer NAME")
    return name


def publish_feedback(c, reviewer: str | None, answers: str | None, dry_run: bool) -> int:
    import config
    import journal
    run, repo = c.need_run(), c.need_repo()
    pr = str(c.pr or (c.data() or {}).get("pr") or "")
    if not pr:
        tm.fail("publish --feedback: no PR number; pass --pr N", 2)
    branch = branch_name(pr)
    who = reviewer_name(reviewer, repo)
    parent = remote_tip(repo, branch, fetch=not dry_run)
    if not parent:
        print(f"publish --feedback: origin has no {branch}. The author publishes the review first.")
        return 1
    rel = f"feedback/{who}.jsonl"
    entries = tree_entries(repo, parent)
    old = _git(repo, "cat-file", "blob", entries[rel][1]) if rel in entries else ""
    have = {line for line in old.splitlines() if line.strip()}
    rows = [r for r in journal.read(c.journal) if r.get("kind") == "confusion"]
    new = [json.dumps({**r, "reviewer": who}, ensure_ascii=False, sort_keys=True) for r in rows]
    new = [x for x in new if x not in have]
    if not new:
        print(f"publish --feedback: no new confusion rows in {c.journal} for {rel}.")
        return 0
    text = (old + "\n" if old and not old.endswith("\n") else old) + "\n".join(new) + "\n"
    blob = {rel: text.encode("utf-8")}
    refusals = [r for r in checks_feedback(config.for_repo(repo), blob)]
    msg = f"Feedback from {who} on PR #{pr}: {len(new)} confusion row" + ("s" if len(new) != 1 else "")
    q = question(repo, branch, [rel], [], parent, msg)
    if refusals:
        print("publish --feedback refuses:\n  " + "\n  ".join(refusals))
        return 1
    print(q)
    print("  rows:\n" + "\n".join(f"    {json.loads(x).get('what', '')[:100]}" for x in new))
    if dry_run:
        print("\ndry run: nothing written, nothing pushed.")
        return 0
    got = answer(answers)
    if got is None:
        print("\npublish --feedback: no terminal and no --answers FILE. Ask the user the question above; on a yes, pass {\"answer\": \"yes\"}.")
        return 2
    if got not in YES:
        print("publish --feedback: the answer is not yes; nothing is published.")
        return 1
    commit, _ = build_commit(repo, entries, blob, parent, msg)
    push(repo, branch, commit)
    print(f"published {commit[:10]} ({len(new)} rows in {rel}) to origin {branch}")
    return 0


def checks_feedback(cfg: dict, blobs: dict[str, bytes]) -> list[str]:
    import config
    import journal
    out = []
    for rel, blob in blobs.items():
        if config.secret(cfg, rel):
            out.append(f"secret_paths: {rel}")
        text = blob.decode("utf-8", errors="ignore")
        if any(p.search(text) for p in journal.KEY_PATTERNS):
            out.append(f"secret scan: {rel} holds a key-like string")
    return out


# ---- for the author's review and for `open` ----------------------------------------------------

def cache_root() -> Path:
    import config
    return config.understando_home() / "review-cache"


def _set_writable(root: Path, writable: bool) -> None:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            if name == ".git":
                continue
            p = Path(dirpath) / name
            mode = p.stat().st_mode
            p.chmod(mode | stat.S_IWUSR if writable else mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def fetch_review_branch(repo: Path | str, pr: str | int) -> Path:
    """Fetch origin's understando/<pr>-review into the local clone `repo`, and check it out read-only
    at ~/.understando/review-cache/<repo name>/<pr> ($UNDERSTANDO_HOME/review-cache/...). A second
    call updates the same folder to the new tip. Returns the folder; explainer.html is in it.

    Stable contract for `understando open <pr>`: arguments (repo: a local clone of the reviewed
    repo, pr: the PR number), the return value (the folder), and PublishError (a RuntimeError) when
    origin has no review branch or git fails. The checkout is a detached git worktree of `repo`;
    its files have no write bit, so nobody edits the review by mistake."""
    import repoinfo
    repo = Path(repo).expanduser().resolve()
    branch = branch_name(pr)
    tip = remote_tip(repo, branch, fetch=True)
    if not tip:
        raise PublishError(f"origin has no {branch}: the author runs `understando publish {pr}` first")
    dest = cache_root() / repoinfo.repo_name(repo) / str(pr)
    _git(repo, "worktree", "prune", check=False)
    listed = _git(repo, "worktree", "list", "--porcelain", check=False)
    if dest.exists() and f"worktree {dest.resolve()}" in listed:
        _set_writable(dest, True)
        _git(dest, "checkout", "-q", "--detach", "--force", tip)
        _git(dest, "clean", "-q", "-fdx")
    else:
        if dest.exists():
            _set_writable(dest, True)
            import shutil
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        _git(repo, "worktree", "add", "-q", "--detach", str(dest), tip)
    _set_writable(dest, False)
    return dest


def feedback_rows(repo: Path | str, pr: str | int, fetch: bool = False) -> list[dict]:
    """The reviewers' confusion rows on origin's review branch, each with its `reviewer`. The
    author's review reads them as signals. With fetch, ask origin first."""
    repo = Path(repo)
    tip = remote_tip(repo, branch_name(pr), fetch=fetch)
    rows = []
    for path, (_, sha) in sorted(tree_entries(repo, tip).items()):
        if path.startswith("feedback/") and path.endswith(".jsonl"):
            for line in _git(repo, "cat-file", "blob", sha).splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def main(c, argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="understando publish", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pr", nargs="?")
    ap.add_argument("--answers", help='JSON file: {"answer": "yes"}')
    ap.add_argument("--dry-run", action="store_true", help="print the checks, the question and the file list; write nothing")
    ap.add_argument("--feedback", action="store_true", help="publish your own confusion rows to feedback/<reviewer>.jsonl")
    ap.add_argument("--reviewer")
    args = ap.parse_args(argv)
    if args.pr and c.pr and str(args.pr) != str(c.pr):
        tm.fail(f"publish: PR {args.pr} differs from the run's PR {c.pr}", 2)
    if args.pr and not c.pr:
        import ctx as context
        c = context.resolve(None if not c.run else str(c.run), str(c.repo) if c.repo else None, args.pr, c.json)
    try:
        if args.feedback:
            return publish_feedback(c, args.reviewer, args.answers, args.dry_run)
        return publish_review(c, args.answers, args.dry_run)
    except PublishError as exc:
        print(str(exc))
        return 1
