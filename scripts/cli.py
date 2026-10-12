#!/usr/bin/env python3
"""understando: verifier-driven development and formal verification. One entry point for every verb.

    understando <verb> [--repo DIR] [--run DIR] [--app NAME] [--json] [--yes] [verb options]

Verbs:
  create     a project-local verify skill with a feature map, proven end to end on one feature
  discover   the user states the invariants of a feature, through edge-case questions
  build      verifier-driven development: invariant, check, red, code, green, probe
  probe      run the controls of a feature's checks; `probe mutate` runs mutation testing
  formalize  the backend proof tier: Lean or TLA+ with conformance; --recheck RECORD
  maintain   the upkeep pass: drive each feature, run the controls again, flag stale verifiers
  snippet    print a code ref at a commit, with its permalink
  export     write the data and refs.resolved.json for visual-explainer
  doctor     what is present, what is missing, what went stale
  setup      install the links, the mutation venv and the optional skills

`understando <verb> --help` shows the options of one verb. --yes is the user's yes for the
commands that the verb shows: each verb shows them once, and runs them only with --yes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import store  # noqa: E402

S = Path(__file__).resolve().parent
VERBS = ("create", "discover", "build", "probe", "formalize", "maintain", "snippet", "export", "doctor", "setup")
READ_ONLY = {"snippet", "doctor"}
INTERNAL_EXIT = 70


def split_globals(argv: list[str]) -> tuple[dict, list[str]]:
    opts: dict = {"repo": None, "run": None, "app": None, "json": False, "yes": False}
    rest, i = [], 0
    while i < len(argv):
        a = argv[i]
        name, eq, value = a.partition("=")
        if name in ("--repo", "--run", "--app"):
            if eq:
                opts[name[2:]] = value
            else:
                if i + 1 >= len(argv):
                    store.fail(f"{name} needs a value", 2)
                opts[name[2:]] = argv[i + 1]
                i += 1
        elif a in ("--json", "--yes"):
            opts[a[2:]] = True
        else:
            rest.append(a)
        i += 1
    return opts, rest


def internal_error(verb: str, c: store.Ctx | None) -> int:
    """A Python exception in a verb is a bug in understando. The traceback goes to a log file; the
    screen gets one line. Relay the line and stop: do not debug understando in the same session."""
    stamp = store.stamp()
    dirs = ([c.run / "logs"] if c and c.run and c.run.is_dir() else []) + [store.home() / "logs"]
    log = None
    for d in dirs:
        try:
            d.mkdir(parents=True, exist_ok=True)
            log = d / f"internal-error-{verb}-{stamp}.log"
            log.write_text(f"understando {verb}: internal error at {store.now()}\nargv: {sys.argv}\n\n" + traceback.format_exc(), encoding="utf-8")
            break
        except OSError:
            log = None
    line = f"understando hit an internal error in {verb}; the log is {log or 'not written'}; this is a bug in understando"
    print(json.dumps({"error": line, "internal_error": True, "log": str(log) if log else None}) if c and c.json else line)
    return INTERNAL_EXIT


def dispatch(verb: str, argv: list[str], c: store.Ctx) -> int:
    if verb == "setup":
        flags = [a for a in argv if a in ("--links-only", "--mutation")] or argv
        return subprocess.run(["bash", str(S / "setup.sh"), *flags]).returncode
    if verb == "snippet":
        import coderef
        return coderef.main(c, argv)
    mod = __import__(verb)
    return mod.main(c, argv)


def main(argv: list[str]) -> int:
    opts, rest = split_globals(argv)
    if not rest or rest[0] in ("help", "-h", "--help"):
        print(__doc__.strip())
        return 0
    verb, args = rest[0], rest[1:]
    if verb in READ_ONLY:
        testguard.read_only()
    if verb not in VERBS:
        print(f"understando: unknown verb {verb!r}. Run `understando help`.", file=sys.stderr)
        return 2
    c = store.resolve(opts["run"], opts["repo"], opts["app"], opts["json"], opts["yes"])
    try:
        return dispatch(verb, args, c)
    except Exception:  # noqa: BLE001  a bug in a verb: one line, the traceback in the log, exit 70
        return internal_error(verb, c)


if __name__ == "__main__":
    os.environ.setdefault("DO_NOT_TRACK", "1")
    sys.exit(main(sys.argv[1:]))
