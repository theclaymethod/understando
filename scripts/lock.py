"""The run lock: <run>/.lock. Each writing verb takes it for the paths that it writes.

    understando lock status
    understando lock take --verb V --paths P1,P2 [--pid N] [--owner NAME]   for an agent that edits by hand
    understando lock release [--pid N]

A path is `run:<file in the run folder>` or `ready:<path on the ready branch>`. A trailing `/`
or `*` covers everything below. Two holders overlap when one path covers the other. A holder
whose pid is no longer alive does not count, and the next writer removes it. A verb refuses when
a live holder overlaps; with UNDERSTANDO_LOCK_WAIT=<seconds> it waits that long first.
"""

from __future__ import annotations

import getpass
import json
import os
import socket
import sys
import time
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import tm  # noqa: E402


class Busy(RuntimeError):
    pass


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def covers(a: str, b: str) -> bool:
    if a.split(":", 1)[0] != b.split(":", 1)[0]:
        return False
    for x, y in ((a, b), (b, a)):
        base = x.rstrip("*")
        if x == y or (x.endswith(("/", "*")) or x.endswith(":")) and y.startswith(base):
            return True
    return False


def overlap(a: list[str], b: list[str]) -> list[str]:
    return [f"{x} ~ {y}" for x in a for y in b if covers(x, y)]


@contextmanager
def _mutex(run: Path):
    m = run / ".lock.mutex"
    deadline = time.monotonic() + 10
    while True:
        try:
            fd = os.open(m, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() > deadline:
                try:
                    if time.time() - m.stat().st_mtime > 30:
                        m.unlink()
                        continue
                except FileNotFoundError:
                    continue
                raise Busy(f"{m} is held; remove it when no understando verb runs")
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        m.unlink(missing_ok=True)


def read(run: Path) -> list[dict]:
    p = run / ".lock"
    if not p.is_file():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("holders", [])
    except json.JSONDecodeError:
        return []


def live(run: Path) -> list[dict]:
    return [h for h in read(run) if alive(int(h["pid"]))]


def _write(run: Path, holders: list[dict]) -> None:
    p = run / ".lock"
    if holders:
        p.write_text(json.dumps({"holders": holders}, indent=2) + "\n", encoding="utf-8")
    else:
        p.unlink(missing_ok=True)


def owner_name() -> str:
    return os.environ.get("UNDERSTANDO_OWNER") or f"{getpass.getuser()}@{socket.gethostname().split('.')[0]}"


def take(run: Path, verb: str, paths: list[str], pid: int | None = None, owner: str | None = None) -> dict:
    run.mkdir(parents=True, exist_ok=True)
    me = {"owner": owner or owner_name(), "verb": verb, "pid": pid or os.getpid(), "paths": paths, "at": tm.now()}
    wait = float(os.environ.get("UNDERSTANDO_LOCK_WAIT") or 0)
    deadline = time.monotonic() + wait
    while True:
        with _mutex(run):
            holders = live(run)
            clash = [(h, overlap(h["paths"], paths)) for h in holders if h["pid"] != me["pid"]]
            clash = [(h, o) for h, o in clash if o]
            if not clash:
                _write(run, holders + [me])
                return me
        if time.monotonic() >= deadline:
            h, o = clash[0]
            raise Busy(f"refuse: {h['owner']} holds the run lock for `{h['verb']}` (pid {h['pid']}, since {h['at']}) "
                       f"on {', '.join(h['paths'])}. Overlap: {'; '.join(o)}. Wait for it to end, or ask the holder.")
        time.sleep(0.5)


def release(run: Path, pid: int | None = None, entry: dict | None = None) -> None:
    """Remove one entry (a nested verb keeps the outer verb's entry), or every entry of `pid`."""
    pid = pid or os.getpid()
    if not run.is_dir():
        return
    with _mutex(run):
        hs = live(run)
        if entry is not None and entry in hs:
            hs.remove(entry)
        elif entry is None:
            hs = [h for h in hs if h["pid"] != pid]
        _write(run, hs)


@contextmanager
def held(run: Path, verb: str, paths: list[str]):
    me = take(run, verb, paths)
    try:
        yield me
    finally:
        release(run, entry=me)


def covering(run: Path, rel: str) -> list[dict]:
    """The live holders, other than this process, whose paths cover `ready:<rel>`."""
    return [h for h in live(run) if h["pid"] != os.getpid() and overlap(h["paths"], [f"ready:{rel}"])]


def main(c, argv: list[str]) -> int:
    import argparse
    import ctx as context
    ap = argparse.ArgumentParser(prog="understando lock", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["status", "take", "release"], nargs="?", default="status")
    ap.add_argument("--verb", default="manual")
    ap.add_argument("--paths", default="")
    ap.add_argument("--pid", type=int)
    ap.add_argument("--owner")
    args = ap.parse_args(argv)
    run = c.need_run()
    if args.action == "take":
        paths = [p for p in args.paths.split(",") if p]
        if not paths:
            tm.fail("lock take needs --paths", 2)
        try:
            me = take(run, args.verb, paths, args.pid, args.owner)
        except Busy as exc:
            print(str(exc))
            return 1
        context.emit(c, me, f"lock: {me['owner']} holds {', '.join(paths)} for {me['verb']} (pid {me['pid']})")
        return 0
    if args.action == "release":
        release(run, args.pid)
        print("lock: released")
        return 0
    hs = live(run)
    context.emit(c, {"holders": hs}, "\n".join(f"{h['owner']} {h['verb']} pid {h['pid']}: {', '.join(h['paths'])}" for h in hs) or "lock: free")
    return 0
