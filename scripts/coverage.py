"""understando coverage: record the source files that each check runs, once, at the head.

    understando coverage [--only V01,V02]

For each check with a command (a test, a golden or a parity test, a boundary script), coverage
runs the command one time in a scratch worktree of a private clone at the check's commit, with
the line tracer of scripts/coverage_site (Python, standard library). It records the changed code
files of which the run executed a line inside a function body (an import alone does not count) in $R/coverage.json:

    {"schema": 1, "head": <map head>, "ran_at": ..., "checks": {"V14": {"status": "green", "files": [paths]}}}

derive.py reads the record (explain): a changed file that a check of a claim runs is covered by
that claim. Run it again after the head moves; a record at another head counts for nothing. Only
commands of the reviewed CI profile run, and a check that needs the model key never runs here.
A file that only another language runs is not in the record; the control-edit rule still counts it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ctx as context  # noqa: E402
import derive  # noqa: E402
import onto  # noqa: E402
import ops  # noqa: E402
import run_control  # noqa: E402
import tm  # noqa: E402

COV_SITE = Path(__file__).resolve().parent / "coverage_site"


def body_lines(path: Path) -> set[int]:
    """The lines inside function bodies. An import runs each def line and each module-level
    statement, so only a body line shows that a check ran the code."""
    import ast
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for stmt in node.body:
                out.update(range(stmt.lineno, (stmt.end_lineno or stmt.lineno) + 1))
    return out


def touched(cov_dir: Path, root: Path) -> set[str]:
    """The files of which the run executed a line inside a function body."""
    hits: dict[str, set[int]] = {}
    for f in cov_dir.glob("*.json"):
        try:
            for p, lines in json.loads(f.read_text(encoding="utf-8")).items():
                hits.setdefault(p, set()).update(lines)
        except (OSError, json.JSONDecodeError):
            continue
    real = Path(os.path.realpath(root))
    out = set()
    for p, lines in hits.items():
        if p.startswith("..") or os.path.isabs(p) or not (real / p).is_file():
            continue
        if not p.endswith(".py") or lines & body_lines(real / p):
            out.add(p)
    return out


def run(data: dict, repo: Path, only: set[str] | None, changed: set[str]) -> dict[str, dict]:
    targets = [v for v in data["verifiers"] if onto.is_tool(v) and "command" in v and (not only or v["id"] in only)]
    out: dict[str, dict] = {}
    with ops.scratch_clone(repo) as (clone, wt):
        for commit in dict.fromkeys(run_control.commit_of(v, data) for v in targets):
            with run_control.Worktree(clone, commit, wt, "coverage") as root:
                run_control.prepare(root, data)
                for v in (v for v in targets if run_control.commit_of(v, data) == commit):
                    with tempfile.TemporaryDirectory(prefix="understando-cov-") as cov:
                        env = {"PYTHONPATH": os.pathsep.join([str(COV_SITE)] + ([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else [])),
                               "UNDERSTANDO_COV_ROOT": str(root), "UNDERSTANDO_COV_DIR": cov}
                        saved = dict(os.environ)
                        try:
                            os.environ.update(env)
                            code, _, seconds = run_control.run_command(root, {**v["command"], "_env": None}, None)
                        finally:
                            os.environ.clear()
                            os.environ.update(saved)
                        files = sorted(p for p in touched(Path(cov), root) if p in changed and derive.is_code(p))
                    out[v["id"]] = {"status": run_control.classify(code, v["command"]), "seconds": seconds, "files": files, "at": commit}
                    print(f"coverage {v['id']}: {out[v['id']]['status']} in {seconds}s, {len(files)} changed code files")
    return out


def main(c: context.Ctx, argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="understando coverage", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated check IDs")
    args = ap.parse_args(argv)
    data, repo = c.need_map(), c.need_repo()
    only = {x for x in (args.only or "").split(",") if x} or None
    import ci
    import config
    import repoinfo
    refusal, notes = ci.gate(c, data, only)
    for n in notes:
        print(f"coverage: {n}", file=sys.stderr)
    if refusal:
        print(refusal)
        return 1
    cfg = config.load(repoinfo.repo_name(repo))
    keyed = {v["id"] for v in data["verifiers"] if "command" in v and config.needs_key(cfg, v["command"]["argv"])}
    for vid in sorted(keyed & (only or keyed)):
        print(f"coverage: skip {vid}: it needs the model key, and coverage never runs a paid check.")
    scope = (only or {v["id"] for v in data["verifiers"] if "command" in v}) - keyed
    import explain
    changed = set(explain.diff_data(str(repo), data["base"], data["head"])["files"])
    rows = run(data, repo, scope, changed)
    path = c.run / "coverage.json"
    old = tm.load(path) if path.is_file() else {}
    checks = (old.get("checks") or {}) if old.get("head") == data["head"] else {}
    checks.update(rows)
    tm.save({"schema": 1, "head": data["head"], "ran_at": tm.now(), "checks": checks}, path)
    print(f"coverage: recorded {len(rows)} checks in {path}. Run understando explain to count them.")
    return 0
