"""Shared operations for probe, close, trim and build: a private clone, probes, and the ready branch.

Every run happens in a private clone (`git clone --shared --no-checkout`) inside a scratch folder,
so the worktree metadata never goes into the user's repo. The only write to the reviewed repo is
a fast-forward of the branch understando/<pr>-ready. The PR's own commits never change.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_control  # noqa: E402
import tm  # noqa: E402
import verdicts  # noqa: E402

BOT = ["-c", "user.name=understando", "-c", "user.email=understando@localhost", "-c", "commit.gpgsign=false"]


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])} failed: {out.stderr.strip()}")
    return out.stdout.strip()


@contextmanager
def scratch_clone(repo: Path):
    """(clone, scratch dir). Both go away at the end, also on failure."""
    scratch = Path(tempfile.mkdtemp(prefix="understando-"))
    try:
        clone = scratch / "clone"
        git(repo, "rev-parse", "--git-dir")
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(repo), str(clone)], check=True,
                       capture_output=True)
        (scratch / "wt").mkdir()
        yield clone, scratch / "wt"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def ready_branch(data: dict) -> str:
    """The ready branch name: `ready_branch` of the per-repo config, default understando/<pr>-ready."""
    pattern = "understando/{pr}-ready"
    try:
        import config
        import repoinfo
        name = repoinfo.slug_name(str(data.get("repo") or ""))
        if name:
            pattern = config.load(name).get("ready_branch") or pattern
    except Exception:  # noqa: BLE001  the default name is always safe
        pass
    return pattern.format(pr=data.get("pr"))


def ready_tip(repo: Path, data: dict) -> str:
    """The tip of the ready branch. The branch starts at the PR head the first time."""
    branch = ready_branch(data)
    try:
        return git(repo, "rev-parse", "--verify", "-q", f"refs/heads/{branch}")
    except RuntimeError:
        git(repo, "branch", branch, data["head"])
        return data["head"]


def commit_on_ready(clone: Path, wt: Path, tip: str, message: str, change) -> str:
    """Check out `tip` in a scratch worktree of the clone, call change(root), commit, and return
    the new commit. Nothing reaches the reviewed repo until publish()."""
    root = wt / f"ready-{abs(hash(message)) % 100000}"
    git(clone, "worktree", "add", "-q", "--detach", str(root), tip)
    try:
        change(root)
        git(root, "add", "-A")
        git(root, *BOT, "commit", "-q", "-m", message + "\n\nWritten by understando on the ready branch, never in the PR's own commits.")
        return git(root, "rev-parse", "HEAD")
    finally:
        git(clone, "worktree", "remove", "--force", str(root))


def publish(clone: Path, data: dict, commit: str) -> None:
    """Fast-forward understando/<pr>-ready in the reviewed repo to `commit`. Never a force push.

    When a worktree has the branch checked out (the review worktree), the commit goes to a
    scratch ref first, and the worktree merges it with --ff-only, so its files follow the branch."""
    branch = ready_branch(data)
    repo = Path(git(clone, "remote", "get-url", "origin"))
    import repoinfo
    wt = repoinfo.worktree_of(repo, branch)
    if wt is None:
        git(clone, "push", "-q", "origin", f"{commit}:refs/heads/{branch}")
    else:
        incoming = f"refs/understando/incoming/{data.get('pr')}"
        git(clone, "push", "-q", "-f", "origin", f"{commit}:{incoming}")
        try:
            git(wt, "merge", "-q", "--ff-only", commit)
        finally:
            git(repo, "update-ref", "-d", incoming)
    data["ready"] = {"branch": branch, "head": commit}


def probe(data: dict, clone: Path, wt: Path, verifier_ids: set[str] | None = None,
          control_ids: set[str] | None = None, env_file: str | None = None) -> None:
    """Baseline, then each control, then the verdicts. None means all."""
    run_control.run_baseline(data, clone, wt, env_file, verifier_ids or set())
    for k in data["controls"]:
        if control_ids is not None:
            chosen = k["id"] in control_ids
        else:
            chosen = not verifier_ids or k["verifier"] in verifier_ids
        if chosen:
            run_control.run_one(data, k, clone, wt, env_file)
    data["probed_at"] = tm.now()
    verdicts.apply(data)


def next_id(data: dict, prefix: str) -> str:
    items = {"C": data["claims"], "V": data["verifiers"], "K": data["controls"],
             "I": data.get("invariants", [])}[prefix]
    n = max([int(i["id"][1:]) for i in items if i["id"][1:].isdigit()] + [0]) + 1
    return f"{prefix}{n:02d}"


def confirmed_invariant(data: dict, inv_id: str | None) -> dict | None:
    """An invariant that the user wrote or confirmed: author user, status accepted."""
    for inv in data.get("invariants", []):
        if inv["id"] == inv_id and inv["author"] == "user" and inv["status"] == "accepted":
            return inv
    return None


def autonomy() -> bool:
    """Full autonomy: `understando mode on --autonomy`. An agent-picked invariant may then back a
    verifier, and verdicts.py caps its claim at Backed."""
    import ctx
    return bool(ctx.load_mode().get("autonomy")) or bool(__import__("os").environ.get("UNDERSTANDO_AUTONOMY"))


def intent_ok(data: dict, claim: dict, inv_id: str | None = None) -> str | None:
    """None when a verifier may be written for the claim; else the refusal text.

    The claim must come from the PR's stated intent, or link to a user-confirmed invariant. Under
    full autonomy an agent-picked invariant also passes, and its claim stays at Backed or below."""
    inv_id = inv_id or claim.get("invariant")
    if claim.get("stated"):
        return None
    if confirmed_invariant(data, inv_id):
        return None
    if autonomy() and any(i["id"] == inv_id and i["author"] == "agent" for i in data.get("invariants", [])):
        return None
    if inv_id:
        return (f"refuse: {claim['id']} links to invariant {inv_id}, which the user has not confirmed. "
                "Run `understando discover` and confirm it first.")
    return (f"refuse: {claim['id']} is not stated in the PR and links to no user-confirmed invariant. "
            "Run `understando discover`, confirm the invariant with the user, then link it.")
