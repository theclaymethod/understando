"""Facts about the repo from git alone: its root, its origin, its name and a worktree of a branch.

The repo root is the main checkout of the cwd (also from a linked worktree). The repo name and
owner/repo come from `git remote get-url origin`. Standard library only.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)


def git(repo: Path, *args: str, check: bool = True) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def repo_root(start: Path) -> Path | None:
    """The main checkout that holds `start`, also when `start` is in a linked worktree."""
    out = subprocess.run(["git", "-C", str(start), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    common = Path(out.stdout.strip())
    if common.name == ".git":
        return common.parent
    top = subprocess.run(["git", "-C", str(start), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(top.stdout.strip()) if top.returncode == 0 else None


def origin_url(repo: Path) -> str | None:
    out = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"], capture_output=True, text=True)
    return out.stdout.strip() or None


def slug(url: str | None) -> str | None:
    """owner/repo from a GitHub URL (https or ssh). None for a path or another host."""
    if not url:
        return None
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def repo_name(repo: Path) -> str:
    """The folder name under the runs root: the origin repo name, else the folder name."""
    url = origin_url(repo)
    if url:
        return re.sub(r"\.git$", "", url.rstrip("/").split("/")[-1].split(":")[-1])
    return repo.name


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
