"""A private clone for each run, and the one write into the repo: a commit on an understando branch.

Every run happens in a private clone (`git clone --shared --no-checkout`) inside a scratch folder,
so the worktree metadata never goes into the user's repo. The only write to the repo is a new
commit on an understando branch (for example understando/verify-<app>), and only after the
user's yes. The user's own branches and commits never change. Nothing pushes to a remote.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
from store import git  # noqa: E402

BOT = ["-c", "user.name=understando", "-c", "user.email=understando@localhost", "-c", "commit.gpgsign=false"]


@contextmanager
def scratch_clone(repo: Path):
    """(clone, scratch dir). Both go away at the end, also on failure."""
    scratch = Path(tempfile.mkdtemp(prefix="understando-"))
    try:
        clone = scratch / "clone"
        git(repo, "rev-parse", "--git-dir")
        git(repo, "clone", "-q", "--shared", "--no-checkout", str(repo), str(clone))
        (scratch / "wt").mkdir()
        yield clone, scratch / "wt"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def commit_on(clone: Path, wt: Path, tip: str, message: str, change) -> str | None:
    """Check out `tip` in a scratch worktree of the clone, call change(root), and commit. Returns
    the new commit, or None when change() changed nothing."""
    root = wt / f"branch-{abs(hash(message)) % 100000}"
    git(clone, "worktree", "add", "-q", "--detach", str(root), tip)
    try:
        change(root)
        git(root, "add", "-A")
        if not git(root, "status", "--porcelain"):
            return None
        git(root, *BOT, "commit", "-q", "-m", message + "\n\nWritten by understando on its own branch, never in your commits.")
        return git(root, "rev-parse", "HEAD")
    finally:
        git(clone, "worktree", "remove", "--force", str(root))


def fast_forward(clone: Path, repo: Path, branch: str, commit: str) -> None:
    """Move `branch` of the repo to `commit`: a new branch, or a fast-forward. Never a force push.
    When a worktree has the branch checked out, that worktree merges with --ff-only."""
    import repoinfo
    wt = repoinfo.worktree_of(repo, branch)
    if wt is None:
        git(clone, "push", "-q", "origin", f"{commit}:refs/heads/{branch}")
        return
    incoming = f"refs/understando/incoming/{branch.replace('/', '-')}"
    git(clone, "push", "-q", "-f", "origin", f"{commit}:{incoming}")
    try:
        git(wt, "merge", "-q", "--ff-only", commit)
    finally:
        git(repo, "update-ref", "-d", incoming)
