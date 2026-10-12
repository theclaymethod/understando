"""Facts about the repo from git alone: its root, its origin, its name, a commit and a worktree of a branch.

The repo root is the main checkout of the cwd (also from a linked worktree). The repo name and
owner/repo come from `git remote get-url origin`. The root, the origin and the commit of a full
sha are memoized for the process. Standard library only.
"""

from __future__ import annotations

import functools
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
from store import git  # noqa: E402

SHA = re.compile(r"[0-9a-f]{40}")


@functools.lru_cache(maxsize=None)
def _root(start: Path) -> Path | None:
    common = git(start, "rev-parse", "--path-format=absolute", "--git-common-dir", check=False)
    if not common:
        return None
    if Path(common).name == ".git":
        return Path(common).parent.resolve()
    top = git(start, "rev-parse", "--show-toplevel", check=False)
    return Path(top).resolve() if top else None


def repo_root(start: Path) -> Path | None:
    """The main checkout that holds `start`, also when `start` is in a linked worktree, or when it
    is a file or does not exist yet (its nearest existing folder). None outside a git repo."""
    p = Path(start).expanduser().resolve()
    while not p.exists() and p != p.parent:
        p = p.parent
    if p.is_file():
        p = p.parent
    return _root(p)


@functools.lru_cache(maxsize=None)
def origin_url(repo: Path) -> str | None:
    return git(repo, "remote", "get-url", "origin", check=False) or None


def slug(url: str | None) -> str | None:
    """owner/repo from a GitHub URL (https or ssh). None for a path or another host."""
    if not url:
        return None
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def remote_slug(repo: Path) -> str | None:
    """owner/name of the GitHub remote `origin`, or None."""
    return slug(origin_url(Path(repo)))


def repo_name(repo: Path) -> str:
    """The folder name under the runs root: the origin repo name, else the folder name."""
    url = origin_url(repo)
    if url:
        return re.sub(r"\.git$", "", url.rstrip("/").split("/")[-1].split(":")[-1])
    return repo.name


_REV: dict[tuple[str, str], str] = {}


def rev(repo: Path, name: str) -> str | None:
    """The commit that `name` names, else None. A full sha is immutable, so its answer is memoized."""
    key = (str(repo), name)
    if key in _REV:
        return _REV[key]
    sha = git(repo, "rev-parse", "-q", "--verify", f"{name}^{{commit}}", check=False) or None
    if sha and SHA.fullmatch(name):
        _REV[key] = sha
    return sha


def worktree_of(repo: Path, branch: str) -> Path | None:
    """The worktree that has `branch` checked out, else None."""
    text = git(repo, "worktree", "list", "--porcelain", check=False)
    path = None
    for line in text.splitlines():
        if line.startswith("worktree "):
            path = Path(line[9:])
        elif line == f"branch refs/heads/{branch}" and path:
            return path
    return None
