"""Resolve the PR head through a chain, and run offline when GitHub cannot be reached.

    1. gh pr view N --json headRefOid,baseRefName,headRefName
    2. git ls-remote origin refs/pull/N/head          (no gh needed; the network must be up)
    3. the last known head: the run's review.json, else the trust map; a local refs/remotes/origin/<head branch>
       that is newer (it contains the known head) wins
    --head SHA overrides all of it.

Offline mode means step 3. Everything local still runs; anything that needs the network is refused
with a plain reason (refusal()). Standard library only.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)

NETWORK_VERBS = ("publish",)


def ls_remote_head(repo: Path, pr: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(repo), "ls-remote", "origin", f"refs/pull/{pr}/head"],
                             capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if out.returncode:
        return None
    for line in out.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        if ref.strip() == f"refs/pull/{pr}/head" and len(sha) >= 40:
            return sha
    return None


def _json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        return {}


def last_known(run: Path, repo: Path) -> dict | None:
    """{head, base, branch, when} from the run's review.json, else the trust map; None when neither has a head."""
    import repoinfo
    st = _json(run / "review.json")
    head, when, source = st.get("head"), st.get("summary_at") or st.get("started_at"), "review.json"
    if not head:
        tmap = _json(run / "trust-map.json")
        head, source = tmap.get("head"), "trust-map.json"
        if head:
            f = run / "trust-map.json"
            when = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not head:
        return None
    branch = st.get("head_branch")
    if branch:
        tip = repoinfo.rev(repo, f"refs/remotes/origin/{branch}")
        if tip and tip != head and (repoinfo.rev(repo, head) is None or
                                    subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", head, tip]).returncode == 0):
            head, source = tip, f"origin/{branch}"
    return {"head": head, "base": st.get("base_name"), "branch": branch, "when": when or "an earlier run", "source": source}


def refusal(run: Path | None, verb: str) -> str | None:
    """A plain refusal for a verb that needs the network when the run is offline, else None."""
    if not run or verb not in NETWORK_VERBS:
        return None
    st = _json(Path(run) / "review.json")
    if st.get("offline"):
        return (f"{verb}: I can't reach GitHub from here, so I can't {verb} this review. "
                f"Run it where the network is available. ({st.get('offline_reason', 'GitHub was not reachable')})")
    return None
