#!/usr/bin/env python3
"""Run verifiers at the PR head, and run controls: one planted defect per scratch worktree.

    python3 scripts/run_control.py --map trust-map.json --repo <git repo> --baseline
    python3 scripts/run_control.py --map trust-map.json --repo <git repo> --control K01
    python3 scripts/run_control.py --map trust-map.json --repo <git repo> --all

Options:
    --scratch DIR     parent of the scratch worktrees (default: a new temp dir)
    --env-file FILE   bash file that a verifier with "env_file": true sources first
    --only V01,V02    with --baseline: run only these verifiers

For each control the script:
  1. adds a detached scratch worktree of --repo at the trust map's `head`;
  2. runs the trust map's `setup` commands in it, without the env file;
  3. applies the control's edits, and refuses when an edit does not apply exactly;
  4. runs the verifier's command, and records green (exit 0), red (an exit in `red_exits`,
     default [1], and the `expect.pattern` holds), or error (anything else);
  5. removes the worktree, also on failure.

The script writes results into the trust map. It never edits the --repo checkout itself,
and it never pushes. Git runs without the env file, so a missing HOME there does no harm.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tm  # noqa: E402

TAIL_LINES = 40


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.strip()


class Worktree:
    def __init__(self, repo: Path, head: str, parent: Path, name: str):
        self.repo, self.head = repo, head
        self.path = parent / f"{name}-{os.getpid()}-{int(time.time() * 1000) % 100000}"

    def __enter__(self) -> Path:
        git(self.repo, "worktree", "add", "--detach", str(self.path), self.head)
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
    if op == "delete-file":
        path.unlink()
        return
    if op == "corrupt-byte":
        data = bytearray(path.read_bytes())
        offset = edit.get("offset", len(data) // 2)
        data[offset] ^= 0x01
        path.write_bytes(bytes(data))
        return
    text = path.read_text(encoding="utf-8")
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


def run_command(root: Path, command: dict, env_file: str | None) -> tuple[int | None, str, float]:
    cwd = root / command.get("cwd", ".")
    argv = command["argv"]
    if command.get("env_file"):
        if not env_file:
            raise ValueError("the verifier needs --env-file")
        argv = ["bash", "-c", 'source "$0" && exec "$@"', env_file, *argv]
    start = time.monotonic()
    try:
        out = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                             timeout=command.get("timeout_s", 900), stdin=subprocess.DEVNULL)
        code, output = out.returncode, out.stdout + out.stderr
    except subprocess.TimeoutExpired as exc:
        code = None
        output = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        output += "\n[understando] timeout"
    seconds = round(time.monotonic() - start, 2)
    return code, output, seconds


def tail(text: str) -> str:
    text = text.replace(str(Path.home()), "~")
    return tm.redact("\n".join(text.rstrip().splitlines()[-TAIL_LINES:]))


def classify(code: int | None, command: dict) -> str:
    if code == 0:
        return "green"
    if code is not None and code in command.get("red_exits", [1]):
        return "red"
    return "error"


def prepare(root: Path, data: dict) -> None:
    for step in data.get("setup", []):
        code, output, _ = run_command(root, {**step, "env_file": False}, None)
        if code != 0:
            raise RuntimeError(f"setup {' '.join(step['argv'])} failed:\n{tail(output)}")


def scrub(text: str, root: Path) -> str:
    return text.replace(str(root), "<worktree>")


def run_baseline(data: dict, repo: Path, scratch: Path, env_file: str | None, only: set[str]) -> None:
    targets = [v for v in data["verifiers"] if "command" in v and (not only or v["id"] in only)]
    if not targets:
        return
    with Worktree(repo, data["head"], scratch, "baseline") as root:
        prepare(root, data)
        for v in targets:
            code, output, seconds = run_command(root, v["command"], env_file)
            v["baseline"] = {
                "status": classify(code, v["command"]), "exit": code, "seconds": seconds,
                "output_tail": tail(scrub(output, root)), "ran_at": tm.now(), "head": data["head"],
            }
            print(f"baseline {v['id']}: {v['baseline']['status']} (exit {code}, {seconds}s)")


def run_one(data: dict, control: dict, repo: Path, scratch: Path, env_file: str | None) -> None:
    v = next(v for v in data["verifiers"] if v["id"] == control["verifier"])
    if "command" not in v:
        control["result"] = {"status": "skipped", "note": "The verifier has no command.", "ran_at": tm.now()}
        return
    with Worktree(repo, data["head"], scratch, control["id"].lower()) as root:
        try:
            prepare(root, data)
            for edit in control["edits"]:
                apply_edit(root, edit)
        except (ValueError, RuntimeError, OSError) as exc:
            control["result"] = {"status": "error", "exit": None, "note": f"The control did not apply: {exc}",
                                 "ran_at": tm.now(), "head": data["head"]}
            print(f"control {control['id']}: error ({exc})")
            return
        code, output, seconds = run_command(root, v["command"], env_file)
    status = classify(code, v["command"])
    matched = None
    pattern = control["expect"].get("pattern")
    if status == "red" and pattern:
        matched = re.search(pattern, output, re.M) is not None
    control["result"] = {
        "status": status, "exit": code, "seconds": seconds, "matched": matched,
        "output_tail": tail(scrub(output, root)), "ran_at": tm.now(), "head": data["head"],
    }
    shown = status if matched is not False else "red, but the expected pattern is missing"
    print(f"control {control['id']} on {v['id']}: {shown} (exit {code}, {seconds}s)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--scratch")
    ap.add_argument("--env-file")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--baseline", action="store_true")
    group.add_argument("--control")
    group.add_argument("--all", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    data = tm.load(args.map)
    errors = tm.validate(data)
    if errors:
        tm.fail("invalid trust map:\n" + "\n".join(errors), 1)
    repo = Path(args.repo).resolve()
    git(repo, "cat-file", "-e", f"{data['head']}^{{commit}}")
    scratch = Path(args.scratch) if args.scratch else Path(tempfile.mkdtemp(prefix="understando-"))
    scratch.mkdir(parents=True, exist_ok=True)
    env_file = str(Path(args.env_file).resolve()) if args.env_file else None

    if args.baseline:
        run_baseline(data, repo, scratch, env_file, {s for s in args.only.split(",") if s})
        tm.save(data, args.map)
        return 0
    chosen = data["controls"] if args.all else [k for k in data["controls"] if k["id"] == args.control]
    if not chosen:
        tm.fail(f"no control {args.control}")
    for control in chosen:
        run_one(data, control, repo, scratch, env_file)
        tm.save(data, args.map)
    return 0


if __name__ == "__main__":
    sys.exit(main())
