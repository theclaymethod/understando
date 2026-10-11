"""Tier-1 proof standard: an e2e verifier must drive the real user path.

An e2e test drives the app the way a user does: it starts the CLI or service in its own process,
sends an HTTP request, or drives a browser or a terminal. A test that only imports the code and
calls its functions is an integration test, even when its name says e2e. probe reads the test
files of each e2e verifier at its commit and records `user_path`:

  user-path      the test starts a process, calls a network endpoint or drives a browser or a PTY
  internal-only  the test only calls internal functions: FLAG NOT-USER-PATH, and the kind becomes
                 integration (`claimed_kind` keeps "e2e")
  unknown        no test file to read (a shell command, an npm script, a binary): no flag

(Adapted from the proof standards of agent-guards create-verification-skill, MIT.)
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)

USER_PATH = re.compile(
    r"\b(subprocess|Popen|os\.system|os\.exec|pexpect|pty\.|ptyprocess|tmux|sys\.executable|shutil\.which|"
    r"requests\.|httpx|urllib\.request|http\.client|aiohttp|websocket|TestClient|CliRunner|playwright|selenium|"
    r"page\.goto|chromium|puppeteer|child_process|execa|spawn\(|fetch\(|supertest|cy\.visit|curl )")


def _show(repo: Path, ref: str, path: str) -> str | None:
    out = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"], capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


def test_files(repo: Path, ref: str, v: dict) -> list[str]:
    """The test files that a verifier command selects: path args, or a dotted unittest module."""
    cmd = v.get("command") or {}
    cwd = cmd.get("cwd", ".").strip("./")
    files = []
    for a in cmd.get("argv", [])[1:]:
        if a.startswith("-"):
            continue
        base = a.split("::")[0]
        cands = [base] if re.search(r"\.(py|ts|tsx|js|mjs|rs|go|sh)$", base) else []
        if not cands and re.fullmatch(r"[A-Za-z_][\w.]*", a) and "." in a:
            parts = a.split(".")
            cands = ["/".join(parts[:i]) + ".py" for i in range(len(parts), 0, -1)]
        for f in cands:
            full = f"{cwd}/{f}" if cwd else f
            if _show(repo, ref, full) is not None:
                files.append(full)
                break
    return files


def classify(repo: Path, ref: str, v: dict) -> dict:
    files = test_files(repo, ref, v)
    if not files:
        return {"result": "unknown", "detail": "no test file to read in the command"}
    hits = [f for f in files if USER_PATH.search(_show(repo, ref, f) or "")]
    if hits:
        return {"result": "user-path", "detail": f"{', '.join(hits)} starts a process, calls an endpoint or drives a UI"}
    return {"result": "internal-only", "detail": f"{', '.join(files)} only imports the code and calls its functions"}


def mark(data: dict, repo: Path, only: set[str] | None = None) -> list[str]:
    """Classify each e2e verifier (and each one that a past probe moved to integration). Returns the
    IDs that only call internal functions."""
    out = []
    for v in data["verifiers"]:
        claimed = (v.get("user_path") or {}).get("claimed_kind") or v["kind"]
        if claimed != "e2e" or "command" not in v or (only and v["id"] not in only):
            continue
        r = classify(repo, v.get("at") or data["head"], v)
        if r["result"] == "internal-only":
            v["user_path"] = {**r, "claimed_kind": "e2e"}
            v["kind"] = "integration"
            out.append(v["id"])
        else:
            v["user_path"] = r
            v["kind"] = "e2e"
    return out
