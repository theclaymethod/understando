"""understando probe mutate: mutation testing. A mutant is a control that a tool plants.

    understando probe mutate --paths wallet/core.py [--feature F] [--tests tests/] [--yes]
    understando probe mutate --tool cosmic-ray --paths wallet/core.py [--lines wallet/core.py:12-14]
                             [--base REF] [--top 5] [--yes]

- mutmut is the fast default. It mutates each function of the paths and runs the tests that its
  own per-test coverage maps to that function. Then probe runs each covering test alone against
  each killed mutant (MUTANT_UNDER_TEST), for the kill matrix.
- cosmic-ray is for targeted runs on the riskiest changed lines: the lines that --lines names, else
  the changed lines (base to head) of the paths, guards and comparisons first, and the lines where
  a mutmut mutant survived. probe records the per-test line coverage of each test (the tracer of
  scripts/coverage_site), runs only the tests that cover the line of a mutant, and runs each one
  alone: the kill matrix.
- Equivalent-mutant filters, before a survivor counts: the same bytecode as the original (with the
  docstrings removed: trivial compiler equivalence), the same syntax tree (a change only in a
  docstring or the layout), and a change
  only in the text of an error, log or print message. A filtered mutant is not a survivor; the
  report lists it with its filter.

Each run is in a scratch worktree of a private clone. The tools come from the mutation venv
(`understando setup --mutation`, or --venv DIR with mutmut, cosmic-ray and pytest). The commands
show once and run only with --yes. The result goes to the `mutation` list of the store.
"""

from __future__ import annotations

import argparse
import ast
import configparser
import json
import marshal
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import coderef  # noqa: E402
import run_control  # noqa: E402
import store  # noqa: E402
import toolprobe  # noqa: E402

COV_SITE = Path(__file__).resolve().parent / "coverage_site"
# The helpers that run in the mutation venv: each one imports its tool once for every mutant.
# MUTMUT_SHOW: the `mutmut show` diff of each mutant name (stdin: the JSON list of names).
MUTMUT_SHOW = r"""
import json, sys
from mutmut.mutation.diff_apply import find_mutant, get_diff_for_mutant
out = {}
for name in json.load(sys.stdin):
    try:
        out[name] = get_diff_for_mutant(name, path=find_mutant(name).path)
    except Exception:
        out[name] = ""
json.dump(out, sys.stdout)
"""
# COSMIC_APPLY: the file text of each mutant, as `cosmic-ray apply` writes it, or None when the
# operator does not apply (stdin: the JSON list of [path, operator, occurrence]).
COSMIC_APPLY = r"""
import json, sys
from pathlib import Path
import cosmic_ray.plugins
from cosmic_ray.mutating import mutate_code
from cosmic_ray.util import read_python_source
out = []
for path, operator, occurrence in json.load(sys.stdin):
    try:
        out.append({"text": mutate_code(read_python_source(Path(path)), cosmic_ray.plugins.get_operator(operator)(), occurrence)})
    except Exception as exc:
        out.append({"text": None, "error": f"{type(exc).__name__}: {exc}"})
json.dump(out, sys.stdout)
"""
MESSAGE_CALLS = re.compile(r"(Error|Exception|Warning|print|warn|warning|info|debug|error|exception|critical|log)$")


# ---- the equivalent-mutant filters -------------------------------------------------------------

class _NoDocs(ast.NodeTransformer):
    def _strip(self, node):
        self.generic_visit(node)
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            node.body = body[1:] or [ast.Pass()]
        return node

    visit_Module = visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _strip


class _NoMessages(_NoDocs):
    def visit_Call(self, node):
        self.generic_visit(node)
        name = ast.unparse(node.func).split(".")[-1]
        if MESSAGE_CALLS.search(name):
            node.args = [ast.Constant("") if isinstance(a, (ast.Constant, ast.JoinedStr)) and not isinstance(getattr(a, "value", ""), (int, float))
                         else a for a in node.args]
        return node


def _code(tree: ast.AST):
    return compile(ast.fix_missing_locations(tree), "<mutant>", "exec")


def _bytes(code) -> bytes:
    """The bytecode, the constants and the names of a code object and its children, without the line table."""
    parts = [code.co_code, repr(code.co_names).encode(), repr(code.co_varnames).encode()]
    for k in code.co_consts:
        parts.append(_bytes(k) if hasattr(k, "co_code") else marshal.dumps(k) if isinstance(k, (int, float, str, bytes, tuple, type(None), bool)) else repr(k).encode())
    return b"\0".join(parts)


def equivalent(before: str, after: str) -> str | None:
    """The filter that holds for a mutant, else None."""
    try:
        a, b = ast.parse(before), ast.parse(after)
    except SyntaxError:
        return None
    if ast.dump(_NoDocs().visit(ast.parse(before))) == ast.dump(_NoDocs().visit(ast.parse(after))):
        return "same-ast"
    try:
        if _bytes(_code(_NoDocs().visit(a))) == _bytes(_code(_NoDocs().visit(b))):
            return "same-bytecode"
    except (SyntaxError, ValueError, TypeError):
        pass
    if ast.dump(_NoMessages().visit(ast.parse(before))) == ast.dump(_NoMessages().visit(ast.parse(after))):
        return "message-text"
    return None


def apply_show(text: str, diff: str) -> tuple[str, int] | None:
    """Apply the diff of `mutmut show` (one function, line numbers of the function) to the file text
    by content. Returns (the mutated text, the file line of the first changed line)."""
    out = text
    first = None
    for hunk in re.split(r"(?m)^@@[^\n]*@@\n", diff)[1:]:
        old, new = [], []
        for row in hunk.splitlines(keepends=True):
            if row.startswith(("---", "+++")) or row.startswith("\\"):
                continue
            tag, body = row[:1], row[1:]
            if tag in (" ", "-"):
                old.append(body)
            if tag in (" ", "+"):
                new.append(body)
        block = "".join(old)
        if not block or out.count(block) != 1:
            return None
        at = out.index(block)
        head = out[:at].count("\n")
        changed = next((i for i, (x, y) in enumerate(zip(old, new)) if x != y), 0)
        first = first or head + changed + 1
        out = out.replace(block, "".join(new), 1)
    return (out, first or 1) if out != text else None


# ---- shared ------------------------------------------------------------------------------------

def venv(arg: str | None) -> Path:
    v = Path(arg).resolve() if arg else toolprobe.mutation_venv()
    if not v or not (v / "bin" / "python").exists():
        store.fail("probe mutate: no mutation venv. Run `understando setup --mutation` (mutmut, cosmic-ray and pytest), "
                   "or pass --venv DIR with them installed.", 2)
    return v


def env_for(v: Path, root: Path, extra: dict | None = None) -> dict:
    env = {**os.environ, "PATH": f"{v / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}", "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": os.pathsep.join([str(root)] + ([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else []))}
    env.pop("VIRTUAL_ENV", None)
    return {**env, **(extra or {})}


def sh(argv: list[str], cwd: Path, env: dict, timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)


def helper(v: Path, script: str, items: list, cwd: Path, env: dict):
    """Run one helper of the mutation venv on the JSON items, and return its JSON answer."""
    out = subprocess.run([str(v / "bin" / "python"), "-c", script], cwd=cwd, env=env, input=json.dumps(items),
                         capture_output=True, text=True, timeout=1800)
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"a mutation helper failed (exit {out.returncode}): {run_control.tail(out.stdout + out.stderr)}") from None


def pytest_one(v: Path, cwd: Path, test: str, env: dict) -> int:
    out = sh([str(v / "bin" / "python"), "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", test], cwd, env, timeout=600)
    return out.returncode


def summary(mutants: list[dict]) -> dict:
    s: dict[str, int] = {"total": len(mutants)}
    for m in mutants:
        key = "equivalent" if m.get("filter") else m["status"].replace(" ", "_")
        s[key] = s.get(key, 0) + 1
    k, sv = s.get("killed", 0), s.get("survived", 0)
    s["score"] = round(k / (k + sv), 3) if k + sv else None
    return s


# ---- mutmut ------------------------------------------------------------------------------------

def run_mutmut(root: Path, v: Path, paths: list[str], tests: str, matrix_max: int) -> dict:
    cfg = configparser.ConfigParser()
    sc = root / "setup.cfg"
    if sc.is_file():
        cfg.read(sc)
    tops = sorted({p.split("/")[0] for p in paths})
    cfg["mutmut"] = {"source_paths": "\n" + "\n".join(tops), "pytest_add_cli_args_test_selection": "\n" + tests,
                     "pytest_add_cli_args": "\n-p\nno:cacheprovider",
                     "only_mutate": "\n" + "\n".join(p if p.endswith(".py") else p.rstrip("/") + "/*" for p in paths)}
    with open(sc, "w") as fh:
        cfg.write(fh)
    env = env_for(v, root)
    env.pop("PYTHONPATH")  # mutmut puts its mutants/ copy first; the repo root on the path would hide it
    run = sh([str(v / "bin" / "mutmut"), "run"], root, env)
    res = sh([str(v / "bin" / "mutmut"), "results", "--all", "true"], root, env)
    if run.returncode not in (0, 1) and not res.stdout.strip():
        raise RuntimeError(f"mutmut run failed (exit {run.returncode}): {run_control.tail(run.stdout + run.stderr)}")
    stats = {}
    sp = root / "mutants" / "mutmut-stats.json"
    if sp.is_file():
        stats = json.loads(sp.read_text())
    by_fn = stats.get("tests_by_mangled_function_name") or {}
    rows = []  # (n, name, status, fn, path) of each mutant in the paths
    for n, line in enumerate(x for x in res.stdout.splitlines() if ": " in x):
        name, _, status = line.strip().partition(": ")
        fn = name.rsplit("__mutmut_", 1)[0]
        path = fn.split(".x_")[0].replace(".", "/") + ".py"
        if any(path == p or path.startswith(p.rstrip("/") + "/") for p in paths):
            rows.append((n, name, status, fn, path))
    diffs = helper(v, MUTMUT_SHOW, [r[1] for r in rows], root, env) if rows else {}
    sources: dict[str, str] = {}
    mutants, matrix, cells = [], {}, 0
    for n, name, status, fn, path in rows:
        diff = "\n".join(x for x in diffs.get(name, "").splitlines() if not x.startswith("# "))
        if path not in sources:
            sources[path] = (root / path).read_text(encoding="utf-8")
        src = sources[path]
        applied = apply_show(src, diff)
        mid = f"m{n + 1}"
        m = {"id": mid, "name": name, "path": path, "line": applied[1] if applied else None, "status": status,
             "diff": diff.strip() + "\n", "tests": by_fn.get(fn, [])}
        if applied and status == "survived":
            f = equivalent(src, applied[0])
            if f:
                m["filter"] = f
        if status in ("killed", "survived") and not m.get("filter"):
            row = {}
            for t in m["tests"]:
                if status == "survived":
                    row[t] = "survived"
                elif cells < matrix_max:
                    cells += 1
                    code = pytest_one(v, root / "mutants", t, env_for(v, root / "mutants", {"MUTANT_UNDER_TEST": name}))
                    row[t] = "survived" if code == 0 else "killed"
            matrix[mid] = row
            m["killed_by"] = [t for t, x in row.items() if x == "killed"]
        mutants.append(m)
    tests_all = sorted({t for m in mutants for t in m["tests"]} | set(stats.get("duration_by_test") or {}))
    return {"tool": "mutmut", "mutants": mutants, "matrix": matrix, "tests": tests_all}


# ---- cosmic-ray, targeted --------------------------------------------------------------------

def changed_lines(repo: Path, base: str, head: str, path: str) -> list[int]:
    out = store.git(repo, "diff", "-U0", "--no-renames", base, head, "--", path, check=False)
    lines: list[int] = []
    for row in out.splitlines():
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", row)
        if m:
            start, count = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            lines += range(start, start + count)
    return lines


def risk_of(src: str) -> dict[int, int]:
    """A score for each line: a guard, a comparison or a boolean operator is riskier than a plain line."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {}
    score: dict[int, int] = {}
    for node in ast.walk(tree):
        line = getattr(node, "lineno", None)
        if line is None:
            continue
        w = 3 if isinstance(node, (ast.If, ast.While, ast.Assert, ast.Raise)) else 2 if isinstance(node, (ast.Compare, ast.BoolOp)) \
            else 1 if isinstance(node, (ast.BinOp, ast.Return, ast.AugAssign)) else 0
        score[line] = max(score.get(line, 0), w)
    return score


def riskiest(repo: Path, data: dict, paths: list[str], base: str, head: str, top: int) -> dict[str, list[int]]:
    survivors: dict[str, set[int]] = {}
    for run in data.get("mutation", []):
        for m in run.get("mutants", []):
            if m["status"] == "survived" and not m.get("filter") and m.get("line"):
                survivors.setdefault(m["path"], set()).add(m["line"])
    out = {}
    for p in [x for x in paths if x.endswith(".py")]:
        src = store.git(repo, "show", f"{head}:{p}", check=False)
        risk = risk_of(src)
        cand = set(changed_lines(repo, base, head, p)) | survivors.get(p, set())
        ranked = sorted((ln for ln in cand if risk.get(ln, 0) > 0 or ln in survivors.get(p, set())),
                        key=lambda ln: (-(ln in survivors.get(p, set())), -risk.get(ln, 0), ln))
        if ranked:
            out[p] = sorted(ranked[:top])
    return out


def collect(v: Path, root: Path, tests: str) -> list[str]:
    out = sh([str(v / "bin" / "python"), "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", tests], root, env_for(v, root))
    return [x.strip() for x in out.stdout.splitlines() if "::" in x]


def coverage_of(v: Path, root: Path, test: str) -> dict[str, set[int]]:
    with tempfile.TemporaryDirectory(prefix="understando-cov-") as cov:
        env = env_for(v, root, {"UNDERSTANDO_COV_ROOT": str(root), "UNDERSTANDO_COV_DIR": cov})
        env["PYTHONPATH"] = os.pathsep.join([str(COV_SITE), env["PYTHONPATH"]])
        pytest_one(v, root, test, env)
        hits: dict[str, set[int]] = {}
        for f in Path(cov).glob("*.json"):
            for p, ls in json.loads(f.read_text()).items():
                hits.setdefault(p, set()).update(ls)
    return hits


def run_cosmic(root: Path, v: Path, lines: dict[str, list[int]], tests: str, matrix_max: int) -> dict:
    env = env_for(v, root)
    ids = collect(v, root, tests)
    cov = {t: coverage_of(v, root, t) for t in ids}
    wanted, sources = [], {}  # (path, line, item) of each mutant on a wanted line, in dump order
    for path, keep in lines.items():
        cfg = root / ".understando-cr.toml"
        cfg.write_text(f'[cosmic-ray]\nmodule-path = "{path}"\ntimeout = 60.0\nexcluded-modules = []\n'
                       f'test-command = "python -m pytest -x -q {tests}"\n[cosmic-ray.distributor]\nname = "local"\n')
        sess = root / ".understando-cr.sqlite"
        init = sh([str(v / "bin" / "cosmic-ray"), "init", str(cfg), str(sess)], root, env)
        if init.returncode:
            raise RuntimeError(f"cosmic-ray init failed: {run_control.tail(init.stdout + init.stderr)}")
        dump = sh([str(v / "bin" / "cosmic-ray"), "dump", str(sess)], root, env).stdout
        sources[path] = (root / path).read_text(encoding="utf-8")
        for row in dump.splitlines():
            item = json.loads(row)[0]["mutations"][0]
            if item["start_pos"][0] in keep:
                wanted.append((path, item["start_pos"][0], item))
        cfg.unlink()
        sess.unlink(missing_ok=True)
    texts = helper(v, COSMIC_APPLY, [[p, it["operator_name"], it["occurrence"]] for p, _, it in wanted], root, env) if wanted else []
    mutants, matrix, cells = [], {}, 0
    for n, ((path, line, item), got) in enumerate(zip(wanted, texts), 1):
        mid, src = f"m{n}", sources[path]
        after = got["text"] if got["text"] is not None else src
        if after == src:
            mutants.append({"id": mid, "path": path, "line": line, "operator": item["operator_name"], "status": "error",
                            "note": run_control.tail(got.get("error", ""))})
            continue
        covering = [t for t in ids if line in cov[t].get(path, set())]
        m = {"id": mid, "path": path, "line": line, "operator": item["operator_name"], "occurrence": item["occurrence"],
             "diff": coderef.unified(path, src, after, context=1), "tests": covering}
        f = equivalent(src, after)
        if f:
            m.update(status="survived", filter=f)
        elif not covering:
            m["status"] = "no tests"
        else:
            (root / path).write_text(after, encoding="utf-8")
            try:
                row = {}
                for t in covering:
                    if cells >= matrix_max:
                        break
                    cells += 1
                    row[t] = "survived" if pytest_one(v, root, t, env) == 0 else "killed"
            finally:
                (root / path).write_text(src, encoding="utf-8")
            matrix[mid] = row
            m["killed_by"] = [t for t, x in row.items() if x == "killed"]
            m["status"] = "killed" if m["killed_by"] else "survived"
        mutants.append(m)
    return {"tool": "cosmic-ray", "mutants": mutants, "matrix": matrix, "tests": ids, "lines": lines}


# ---- the verb ----------------------------------------------------------------------------------

def parse_lines(spec: str) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for part in [x for x in spec.split(",") if x]:
        path, _, rng = part.rpartition(":")
        a, _, b = rng.partition("-")
        out.setdefault(path, []).extend(range(int(a), int(b or a) + 1))
    return out


def main(c: store.Ctx, argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="understando probe mutate", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paths", nargs="+", help="the source files or folders to mutate (default: the feature's paths)")
    ap.add_argument("--feature")
    ap.add_argument("--tool", choices=["mutmut", "cosmic-ray"], default="mutmut")
    ap.add_argument("--tests", default="tests", help="the test folder or file that pytest runs")
    ap.add_argument("--lines", help="cosmic-ray: PATH:A-B,... (default: the riskiest changed lines)")
    ap.add_argument("--base", help="cosmic-ray: the commit before the change (default: the store base, else HEAD~1)")
    ap.add_argument("--top", type=int, default=5, help="cosmic-ray: the number of riskiest lines for each file")
    ap.add_argument("--matrix-max", type=int, default=400, help="the most single-test runs for the kill matrix")
    ap.add_argument("--venv")
    ap.add_argument("--at")
    args = ap.parse_args(argv)
    data = c.need_data()
    repo = c.need_repo()
    head = store.git(repo, "rev-parse", args.at or "HEAD")
    data["head"] = head
    feat = store.find(data, "features", args.feature) if args.feature else None
    paths = args.paths or (feat or {}).get("paths")
    if not paths:
        store.fail("probe mutate: pass --paths, or a --feature with paths", 2)
    v = venv(args.venv)
    lines = None
    if args.tool == "cosmic-ray":
        base = store.git(repo, "rev-parse", args.base or data.get("base") or f"{head}~1", check=False) or head
        lines = parse_lines(args.lines) if args.lines else riskiest(repo, data, paths, base, head, args.top)
        if not lines:
            store.fail("probe mutate: no risky changed line in the paths; name the lines with --lines PATH:A-B", 2)
    py = str(v / "bin" / "python")
    cmds = ([[str(v / "bin" / "mutmut"), "run"], [py, "-m", "pytest", "-x", "-q", "<one covering test>"]] if args.tool == "mutmut" else
            [[str(v / "bin" / "cosmic-ray"), "init|dump|apply", "..."], [py, "-m", "pytest", "-x", "-q", "<one covering test>"]])
    if not store.confirm(c, f"probe mutate ({args.tool})", run_control.commands(data, []) + cmds):
        return 0
    with run_control.scratch_root(repo, head, data, "mutate") as (root, _, _):
        out = run_mutmut(root, v, paths, args.tests, args.matrix_max) if args.tool == "mutmut" else \
            run_cosmic(root, v, lines, args.tests, args.matrix_max)
        shutil.rmtree(root / "mutants", ignore_errors=True)
    rec = {"id": store.next_id(data, "mutation"), "tool": args.tool, "paths": paths, "at": head, "ran_at": store.now(),
           "summary": summary(out["mutants"]), "mutants": out["mutants"], "tests": out["tests"], "matrix": out["matrix"],
           **({"feature": args.feature} if args.feature else {}), **({"lines": out["lines"]} if out.get("lines") else {})}
    data["mutation"].append(rec)
    c.save(data)
    s = rec["summary"]
    text = [f"mutation {rec['id']} ({args.tool}) at {head[:10]}: " + ", ".join(f"{k} {x}" for k, x in s.items() if k not in ("total", "score"))
            + f"; score {s['score']}"]
    for m in out["mutants"]:
        if m["status"] == "survived" and not m.get("filter"):
            text.append(f"SURVIVED {m['id']} {m['path']}:{m['line']}: no test sees this change. Add a test that fails on it.")
        elif m.get("filter"):
            text.append(f"filtered {m['id']} {m['path']}:{m['line']}: {m['filter']}")
    store.emit(c, rec, "\n".join(text))
    return 0
