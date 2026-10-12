"""Run checks at their commit, and run controls: one planted bug for each scratch worktree.

probe, build, create and maintain call this module. For each control it:
  1. adds a detached scratch worktree of the private clone at the check's `at` commit, else at the
     store `head`;
  2. runs the store's `setup` commands in it;
  3. applies the control's edits, and refuses an edit that does not apply exactly. An anchor edit
     (scripts/coderef.py) resolves here, at the commit; an anchor that matches 0 or more than 1
     places is an ANCHOR ERROR;
  4. records the git diff of the worktree (result.diff), runs the check's command, and records
     green (exit 0), red (an exit in `red_exits`, default [1], and `expect.pattern` holds), or
     error (anything else). A degraded control of an eval also records the score;
  5. removes the worktree, also on failure.

A check that names `evidence.require` runs with VERIFY_EVIDENCE_DIR set to a folder of the run;
the files that it leaves there are the evidence of the run. Nothing here edits the user's
checkout, and nothing pushes.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import coderef  # noqa: E402
import store  # noqa: E402
from store import git  # noqa: E402

TAIL_LINES = 40
DIFF_LINES = 80


# maintain sets this: (ref, paths). Each worktree then takes those paths from ref, so the verify
# skill of the understando branch runs against the current code.
OVERLAY: list = [None]


class Worktree:
    def __init__(self, repo: Path, head: str, parent: Path, name: str):
        self.repo, self.head = repo, head
        self.path = parent / f"{name}-{os.getpid()}-{int(time.time() * 1000) % 100000}"

    def __enter__(self) -> Path:
        git(self.repo, "worktree", "add", "--detach", str(self.path), self.head)
        if OVERLAY[0] and OVERLAY[0][0] != self.head:
            ref, paths = OVERLAY[0]
            git(self.path, "checkout", ref, "--", *paths)  # staged, so a control's diff leaves them out
        return self.path

    def __exit__(self, *exc) -> None:
        try:
            git(self.repo, "worktree", "remove", "--force", str(self.path))
        except RuntimeError:
            shutil.rmtree(self.path, ignore_errors=True)
            git(self.repo, "worktree", "prune")


def apply_edit(root: Path, edit: dict) -> None:
    path = root / edit["path"]
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"edit path leaves the worktree: {edit['path']}")
    op = edit["op"]
    if op == "restore-file":
        # Put back the file as it was at `at` (for example the map head, before a fix on the ready
        # branch): the new test of the fix must go red on the code without the fix.
        try:
            path.write_bytes(git(root, "show", f"{edit['at']}:{edit['path']}", raw=True))
        except RuntimeError:
            raise ValueError(f"{edit['path']}: no copy at {edit['at']}") from None
        return
    if op == "delete-file":
        path.unlink()
        return
    if op == "corrupt-byte":
        data = bytearray(path.read_bytes())
        offset = coderef.corrupt_offset(bytes(data), edit)
        data[offset] ^= 0x01
        path.write_bytes(bytes(data))
        return
    text = path.read_text(encoding="utf-8")
    if op in coderef.ANCHOR_OPS:
        # The anchor resolves here, in the scratch worktree at the commit: 0 or 2+ places raise.
        path.write_text(coderef.apply_text(text, edit), encoding="utf-8")
        return
    if op == "append":
        path.write_text(text + edit["text"], encoding="utf-8")
        return
    if op == "replace":
        want = edit.get("count", 1)
        found = text.count(edit["find"])
        if found != want:
            raise ValueError(f"{edit['path']}: find text occurs {found} times, expected {want}")
        path.write_text(text.replace(edit["find"], edit["replace"]), encoding="utf-8")
        return
    raise ValueError(f"unknown op {op}")


def run_command(root: Path, command: dict, env_file: str | None = None, extra_env: dict | None = None) -> tuple[int | None, str, float]:
    cwd = root / command.get("cwd", ".")
    argv = command["argv"]
    if env_file:
        argv = ["bash", "-c", 'source "$0" && exec "$@"', env_file, *argv]
    env = {**os.environ, **(command.get("env") or {}), **(extra_env or {})}
    start = time.monotonic()
    try:
        out = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, env=env,
                             timeout=command.get("timeout_s", 900), stdin=subprocess.DEVNULL)
        code, output = out.returncode, out.stdout + out.stderr
    except subprocess.TimeoutExpired as exc:
        code = None
        output = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        output += "\n[understando] timeout"
    except OSError as exc:
        code, output = None, f"[understando] the command did not start: {exc}"
    return code, output, round(time.monotonic() - start, 2)


def tail(text: str) -> str:
    text = text.replace(str(Path.home()), "~")
    return store.redact("\n".join(text.rstrip().splitlines()[-TAIL_LINES:]))


def classify(code: int | None, command: dict) -> str:
    if code == 0:
        return "green"
    if code is not None and code in command.get("red_exits", [1]):
        return "red"
    return "error"


def prepare(root: Path, data: dict) -> None:
    for step in data.get("setup", []):
        code, output, _ = run_command(root, step)
        if code != 0:
            raise RuntimeError(f"setup {' '.join(step['argv'])} failed:\n{tail(output)}")


def scrub(text: str, root: Path) -> str:
    return text.replace(str(root), "<worktree>")


def commit_of(v: dict, data: dict) -> str:
    """A check runs at its own `at` commit (the ready head), else at the store head."""
    return v.get("at") or data["head"]


def evidence_env(v: dict, evidence: Path | None, name: str) -> tuple[dict, Path | None]:
    if not evidence or not (v.get("evidence") or {}).get("require"):
        return {}, None
    d = evidence / v["id"] / f"{name}-{store.stamp()}"
    d.mkdir(parents=True, exist_ok=True)
    return {"VERIFY_EVIDENCE_DIR": str(d)}, d


def kept(d: Path | None) -> list[str]:
    return sorted(str(p) for p in d.rglob("*") if p.is_file()) if d else []


def run_baseline(data: dict, repo: Path, scratch: Path, only: set[str], env_file: str | None = None,
                 evidence: Path | None = None) -> None:
    targets = [v for v in data["checks"] if "command" in v and (not only or v["id"] in only)]
    for commit in dict.fromkeys(commit_of(v, data) for v in targets):
        with Worktree(repo, commit, scratch, "baseline") as root:
            prepare(root, data)
            for v in (v for v in targets if commit_of(v, data) == commit):
                env, d = evidence_env(v, evidence, "baseline")
                code, output, seconds = run_command(root, v["command"], env_file, env)
                v["baseline"] = {"status": classify(code, v["command"]), "exit": code, "seconds": seconds,
                                 "output_tail": tail(scrub(output, root)), "ran_at": store.now(), "head": commit,
                                 **({"evidence": kept(d)} if d else {})}
                print(f"baseline {v['id']}: {v['baseline']['status']} (exit {code}, {seconds}s)")


def run_one(data: dict, control: dict, repo: Path, scratch: Path, env_file: str | None = None, commit: str | None = None) -> None:
    v = next(v for v in data["checks"] if v["id"] == control["check"])
    if "command" not in v:
        if not (control.get("result") or {}).get("recorded"):
            control["result"] = {"status": "skipped", "note": "The check has no command.", "ran_at": store.now()}
        return
    commit = commit or commit_of(v, data)
    with Worktree(repo, commit, scratch, control["id"].lower()) as root:
        try:
            prepare(root, data)
            for edit in control["edits"]:
                apply_edit(root, edit)
        except coderef.AnchorError as exc:
            control["result"] = {"status": "error", "exit": None, "note": f"The anchor did not resolve once: {exc}",
                                 "ran_at": store.now(), "head": commit}
            print(f"ANCHOR ERROR: control {control['id']}: {exc}", file=sys.stderr)
            return
        except (ValueError, RuntimeError, OSError) as exc:
            control["result"] = {"status": "error", "exit": None, "note": f"The control did not apply: {exc}",
                                 "ran_at": store.now(), "head": commit}
            print(f"control {control['id']}: error ({exc})")
            return
        diff = git(root, "diff", "--no-color", "-U2", check=False, raw=True).decode("utf-8", "replace")
        code, output, seconds = run_command(root, v["command"], env_file)
    status = classify(code, v["command"])
    matched = None
    pattern = control["expect"].get("pattern")
    if status == "red" and pattern:
        matched = re.search(pattern, output, re.M) is not None
    control["result"] = {
        "status": status, "exit": code, "seconds": seconds, "matched": matched,
        "output_tail": tail(scrub(output, root)), "ran_at": store.now(), "head": commit,
        **({"diff": "\n".join(diff.splitlines()[:DIFF_LINES]) + "\n"} if diff.strip() else {}),
    }
    if control["kind"] == "degraded":
        import strength
        control["result"]["score"] = strength.score_of(v, {"output_tail": output})
    shown = status if matched is not False else "red, but the expected pattern is missing"
    print(f"control {control['id']} on {v['id']}: {shown} (exit {code}, {seconds}s)")
