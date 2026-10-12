"""understando probe: prove that each check of a feature can fail.

    understando probe [--feature F] [--check V1,V2] [--control K1] [--env-file FILE] [--yes]
    understando probe mutate ...        mutation testing (scripts/mutation.py; `probe mutate --help`)

probe runs each check at its commit (the baseline), then plants each control in its own scratch
worktree of a private clone, and records which checks go red. A control is a planted bug, a stub,
a mutant or a degraded variant (references/controls.md). A check that stays green on each of its
controls cannot fail, and it does not count. The commands are the commands of the checks: probe
shows them once and runs them only with --yes. The user's checkout does not change.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import ops  # noqa: E402
import run_control  # noqa: E402
import store  # noqa: E402
import strength  # noqa: E402


def pick(data: dict, feature: str | None, checks: set[str] | None) -> set[str]:
    out = {v["id"] for v in data["checks"] if (not feature or v.get("feature") == feature) and (not checks or v["id"] in checks)}
    if checks and checks - out:
        store.fail(f"probe: no check {', '.join(sorted(checks - out))}" + (f" in feature {feature}" if feature else ""), 2)
    return out


def run(c: store.Ctx, data: dict, check_ids: set[str], control_ids: set[str] | None = None, baseline: bool = True,
        env_file: str | None = None, what: str = "probe") -> bool:
    """The baseline of each check, then each chosen control. False when the user has not said yes."""
    repo = c.need_repo()
    targets = [v for v in data["checks"] if v["id"] in check_ids and "command" in v]
    controls = [k for k in data["controls"] if k["check"] in check_ids and (control_ids is None or k["id"] in control_ids)]
    cmds = [step["argv"] for step in data.get("setup", [])] + [v["command"]["argv"] for v in targets]
    if not store.confirm(c, what, cmds):
        return False
    with ops.scratch_clone(repo) as (clone, wt):
        if baseline and targets:
            run_control.run_baseline(data, clone, wt, {v["id"] for v in targets}, env_file, c.run / "evidence")
        for k in controls:
            run_control.run_one(data, k, clone, wt, env_file)
    return True


def report(c: store.Ctx, data: dict, feature: str | None = None) -> dict:
    rep = strength.apply(data)
    if feature:
        rep = {**rep, "claims": [x for x in rep["claims"] if x["feature"] == feature]}
    return rep


def main(c: store.Ctx, argv: list[str]) -> int:
    if argv[:1] == ["mutate"]:
        import mutation
        return mutation.main(c, argv[1:])
    ap = argparse.ArgumentParser(prog="understando probe", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--feature")
    ap.add_argument("--check", help="comma-separated check IDs")
    ap.add_argument("--control", help="comma-separated control IDs")
    ap.add_argument("--env-file", help="a bash file that each check sources first (the user's own)")
    ap.add_argument("--at", help="the commit to run at (default: HEAD of the repo)")
    args = ap.parse_args(argv)
    data = c.need_data()
    data["head"] = store.git(c.need_repo(), "rev-parse", args.at or "HEAD")
    ids = pick(data, args.feature, {x for x in (args.check or "").split(",") if x} or None)
    ks = {x for x in (args.control or "").split(",") if x} or None
    if not run(c, data, ids, ks, env_file=str(Path(args.env_file).resolve()) if args.env_file else None):
        return 0
    rep = report(c, data, args.feature)
    c.save(data)
    store.emit(c, rep, "\n".join(strength.lines(rep)))
    return 0
