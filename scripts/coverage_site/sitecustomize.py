"""Line coverage for understando trim, standard library only.

trim puts this folder first on PYTHONPATH when it runs the e2e suite, so each Python process of
the suite, also a subprocess, records the lines it runs under $UNDERSTANDO_COV_ROOT. Each process
writes one JSON file into $UNDERSTANDO_COV_DIR at exit.
"""

import atexit
import json
import os
import sys
import threading

_root = os.environ.get("UNDERSTANDO_COV_ROOT")
_out = os.environ.get("UNDERSTANDO_COV_DIR")
if _root and _out:
    _root = os.path.realpath(_root) + os.sep
    _hits = {}

    def _tracer(frame, event, arg):
        path = frame.f_code.co_filename
        if not path.startswith(_root) and not os.path.realpath(path).startswith(_root):
            return None
        rel = os.path.relpath(os.path.realpath(path), _root)
        lines = _hits.setdefault(rel, set())

        def local(f, e, a):
            if e == "line":
                lines.add(f.f_lineno)
            return local

        lines.add(frame.f_lineno)
        return local

    sys.settrace(_tracer)
    threading.settrace(_tracer)

    @atexit.register
    def _dump():
        sys.settrace(None)
        with open(os.path.join(_out, f"{os.getpid()}.json"), "w") as fh:
            json.dump({k: sorted(v) for k, v in _hits.items()}, fh)
