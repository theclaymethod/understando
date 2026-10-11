"""A heartbeat for a long step: a progress line every 30 seconds, so the agent knows it is alive."""

from __future__ import annotations

import contextlib
import os
import sys
import threading
import time


@contextlib.contextmanager
def beat(label: str):
    try:
        every = float(os.environ.get("UNDERSTANDO_HEARTBEAT") or 30)
    except ValueError:
        every = 30.0
    stop = threading.Event()
    t0 = time.monotonic()

    def run() -> None:
        while not stop.wait(every):
            print(f"still running: {label}, {int(time.monotonic() - t0)}s so far", file=sys.stderr, flush=True)

    th = threading.Thread(target=run, daemon=True)
    th.start()
    try:
        yield
    finally:
        stop.set()
