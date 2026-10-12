"""The test-isolation guard: a test never writes, and never reads, the real understando data.

Standard library only. Every script imports this module first, so the guard is in each understando
Python process. In a test run, an audit hook refuses each write outside the test's temp root.

- A test run is a process with UNDERSTANDO_TEST set (tests/isolate.sh sets it).
- A write is each open for write, and each rename, replace, remove, mkdir, rmdir, symlink, link,
  truncate and rmtree. Its target must be under $UNDERSTANDO_TEST_ROOT. When the marker is set
  and the root is not set, each write is refused. This covers the run folders, verify.json
  (store.save), the evidence, toolprobe.json, config.toml and each other file.
- A read under the real ~/.understando (the home folder of the user account, not $HOME) is
  refused too, except in a command that calls read_only() first.

A refusal prints one line that starts with "understando test guard:" and stops the process with
exit 1. It is a BaseException, so an `except OSError` or `except Exception` cannot hide it.
"""

from __future__ import annotations

import os
import pwd
import sys

MARKER = "UNDERSTANDO_TEST"
PREFIX = "understando test guard:"
_READ_ONLY = [False]
_INSTALLED = [False]
_WRITE_MODES = set("waxl+")
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
# The written paths of each event: (index of the path, index of its dir_fd or None). The source of a
# symlink is only the text of the link, so it is not a write. rmtree removes by names under a dir_fd.
_PATH_EVENTS = {"os.remove": [(0, 1)], "os.rmdir": [(0, 1)], "os.mkdir": [(0, 2)], "os.truncate": [(0, None)],
                "shutil.rmtree": [(0, 1)], "os.rename": [(0, 2), (1, 3)], "os.replace": [(0, 2), (1, 3)],
                "os.symlink": [(1, 2)], "os.link": [(1, 3)]}


class Refused(BaseException):
    """A write (or a read) that the guard refuses. Not an OSError, so no handler takes it by accident."""


def active() -> bool:
    return bool(os.environ.get(MARKER))


def test_root() -> str | None:
    raw = os.environ.get("UNDERSTANDO_TEST_ROOT")
    return os.path.realpath(raw) if raw else None


def real_store() -> str:
    """The real ~/.understando: from the user account, so a fake $HOME does not move it."""
    return os.path.realpath(os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".understando"))


def under(path: str, base: str) -> bool:
    p, b = os.path.realpath(path), os.path.realpath(base)
    return p == b or p.startswith(b.rstrip(os.sep) + os.sep)


def read_only() -> None:
    """A command that only reads calls this first. Then it may read the real ~/.understando in a test
    run. Writes outside the test root stay refused."""
    _READ_ONLY[0] = True


def _fd_dir(fd) -> str | None:
    """The path of an open folder (a dir_fd), or None."""
    if not isinstance(fd, int) or fd < 0:
        return None
    try:
        import fcntl
        if hasattr(fcntl, "F_GETPATH"):
            return os.fsdecode(fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024)).split(b"\0", 1)[0])
        return os.readlink(f"/proc/self/fd/{fd}")
    except (OSError, ValueError):
        return None


def _text(path, dir_fd=None) -> str | None:
    if isinstance(path, int):
        return None  # a file descriptor: the open of its path was audited
    try:
        p = os.fsdecode(os.fspath(path))
    except TypeError:
        return None
    base = _fd_dir(dir_fd) if dir_fd is not None and not os.path.isabs(p) else None
    return os.path.abspath(os.path.join(base, p) if base else p)


def write_refusal(path, dir_fd=None) -> str | None:
    """None when a test run may write `path` (relative to `dir_fd` when it is set); else the refusal line."""
    p = _text(path, dir_fd)
    if p is None or p.startswith("/dev/"):
        return None
    root = test_root()
    if not root:
        return (f"{PREFIX} refuse to write {p}: a test marker is set ({MARKER}) "
                "and UNDERSTANDO_TEST_ROOT is not set. Source tests/isolate.sh at the top of the test script.")
    if under(p, root):
        return None
    return (f"{PREFIX} refuse to write {p}: the path is outside the test root {root}. "
            "A test writes only under UNDERSTANDO_TEST_ROOT.")


def read_refusal(path) -> str | None:
    p = _text(path)
    if p is None or _READ_ONLY[0]:
        return None
    root = test_root()
    store = real_store()
    if under(p, store) and not (root and under(p, root)):
        return (f"{PREFIX} refuse to read {p}: it is in the real {store}, and this command is not read-only. "
                "A test reads only its own UNDERSTANDO_HOME and UNDERSTANDO_RUNS.")
    return None


def _is_write_open(mode, flags) -> bool:
    if isinstance(mode, str) and _WRITE_MODES & set(mode):
        return True
    return mode is None and isinstance(flags, int) and bool(flags & _WRITE_FLAGS)


def _bytecode(path) -> bool:
    p = _text(path) or ""
    return "__pycache__" in p or p.endswith((".pyc", ".pyc.tmp"))


def _refuse(why: str):
    print(why, file=sys.stderr, flush=True)
    raise Refused(why)


def _hook(event: str, args: tuple) -> None:
    if event == "open":
        path, mode, flags = (tuple(args) + (None, None, None))[:3]
        if _is_write_open(mode, flags):
            why = write_refusal(path)
            if why and _bytecode(path):
                raise PermissionError(why)  # the import system skips the bytecode cache on an OSError
            if why:
                _refuse(why)
        else:
            why = read_refusal(path)
            if why:
                _refuse(why)
        return
    for at, fd_at in _PATH_EVENTS.get(event, ()):
        if at < len(args):
            path = args[at]
            why = write_refusal(path, args[fd_at] if fd_at is not None and fd_at < len(args) else None)
            if why and _bytecode(path):
                raise PermissionError(why)
            if why:
                _refuse(why)


def _excepthook(kind, value, tb, _old=sys.excepthook):
    if not issubclass(kind, Refused):  # a refusal: its line is on stderr already, and the exit is 1
        _old(kind, value, tb)


def install() -> None:
    if _INSTALLED[0] or not active():
        return
    _INSTALLED[0] = True
    sys.addaudithook(_hook)
    sys.excepthook = _excepthook


install()
