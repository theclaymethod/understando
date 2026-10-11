"""understando trim: gate 2 (no excess code) and gate 3 (no unit test that an e2e test already covers).

    understando trim [--report] [--candidates FILE] [--coverage FILE]
    understando trim --accept PATH[:NAME] --reason TEXT       record the user's decision on one item

Gate 3. A unit test is deletable only when each control that turns it red also turns some e2e
test red. trim plants each such control at the ready-branch tip and runs every e2e verifier. A
unit test with a control that no e2e test catches stays, flagged "convert to e2e first". A unit
test that no control turned red checks nothing; trim reports it.

Gate 2. The candidates are the functions in the changed source files, plus the entries of
--candidates (a dead-code tool, or a deletion pass by a model of a different family: guess tier;
[{"path", "name", "why", "source"}]). trim runs the e2e suite with line coverage (Python:
scripts/coverage_site; other languages: --coverage {path: [lines]}). A covered candidate is
deletable when the suite stays green without it. A candidate that no e2e test runs is "excess or
untested": the user decides, and `--accept` records the decision.

Without --report, trim deletes the redundant unit tests and the deletable code in commits on
understando/<pr>-ready, moves each covered control to the e2e verifier that caught it, and runs
the e2e baseline again at the new tip. Then route the cleanup to the skills simplify, ultra-clean,
deslop and pstack:no-comments. Results go to $R/trim.json.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import config  # noqa: E402
import ctx as context  # noqa: E402
import journal  # noqa: E402
import ops  # noqa: E402
import run_control  # noqa: E402
import tm  # noqa: E402
import verdicts  # noqa: E402

E2E_KINDS = ("e2e", "integration")
COV_SITE = Path(__file__).resolve().parent / "coverage_site"
DEAD = ("cannot-fail", "failing", "broken")
CFG: dict = config.load(None)


def is_test(path: str) -> bool:
    parts = path.split("/")
    return any(p in ("tests", "test", "spec", "__tests__") for p in parts[:-1]) or parts[-1].startswith("test_")


def location(v: dict, root) -> tuple[str, str | None] | None:
    """Where a unit test lives: its `test` field, or the unittest or pytest argv. `root` is the
    worktree, or a function that says whether a path exists."""
    exists = root if callable(root) else (lambda rel: (root / rel).is_file())
    if v.get("test"):
        return v["test"]["path"], v["test"].get("name")
    for arg in reversed(v["command"]["argv"]):
        if "::" in arg:
            path, name = arg.split("::", 1)
            return path, name.split("::")[0]
        parts = arg.split(".")
        for i in range(len(parts), 0, -1):
            cand = "/".join(parts[:i]) + ".py"
            if exists(cand):
                return cand, parts[i] if i < len(parts) else None
    return None


class Protected(ValueError):
    """The code to delete holds a @cc contract comment. trim never deletes one."""


def remove_def(text: str, name: str) -> str:
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            lines = text.splitlines(keepends=True)
            if any("@cc" in line for line in lines[start - 1:node.end_lineno]):
                raise Protected(f"{name} holds a @cc contract comment")
            del lines[start - 1:node.end_lineno]
            while start - 2 >= 0 and start - 2 < len(lines) and not lines[start - 2].strip() and start - 1 < len(lines) and not lines[start - 1].strip():
                del lines[start - 1]
            return "".join(lines)
    raise ValueError(f"no top-level {name}")


def functions(path: str, text: str) -> list[dict]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body[1:] if (isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant)
                                     and isinstance(node.body[0].value.value, str) and len(node.body) > 1) else node.body
            out.append({"path": path, "name": node.name, "lines": list(range(body[0].lineno, node.end_lineno + 1)),
                        "source": "changed code"})
    return out


def run(root: Path, v: dict, env: dict | None = None) -> str:
    saved = dict(os.environ)
    try:
        if env:
            os.environ.update(env)
        code, _, _ = run_control.run_command(root, v["command"], None)
    finally:
        os.environ.clear()
        os.environ.update(saved)
    return run_control.classify(code, v["command"])


def worktree(clone: Path, wt: Path, commit: str, name: str):
    return run_control.Worktree(clone, commit, wt, name)


def gate3(data: dict, clone: Path, wt: Path, tip: str, e2e: list[dict]) -> dict:
    controls: dict[str, list[dict]] = {}
    for k in data["controls"]:
        controls.setdefault(k["verifier"], []).append(k)
    out = {"redundant": [], "unique": [], "checks_nothing": []}
    for u in [v for v in data["verifiers"] if v["kind"] == "unit" and "command" in v]:
        caught = [k for k in controls.get(u["id"], []) if verdicts.control_outcome(k) == "caught"]
        if not caught:
            out["checks_nothing"].append({"id": u["id"], "why": "no control turned it red"})
            continue
        covered, uncovered = {}, []
        for k in caught:
            with worktree(clone, wt, tip, f"trim-{k['id'].lower()}") as root:
                run_control.prepare(root, data)
                for e in k["edits"]:
                    run_control.apply_edit(root, e)
                red = [e["id"] for e in e2e if run(root, e) == "red"]
            if red:
                covered[k["id"]] = red
            else:
                uncovered.append(k["id"])
        files = set(ops.git(clone, "ls-tree", "-r", "--name-only", tip).split())
        loc = location(u, lambda rel: rel in files)
        if loc and config.refuse_edit(CFG, loc[0]):
            out.setdefault("protected", []).append({"id": u["id"], "note": config.refuse_edit(CFG, loc[0])})
            continue
        if loc and loc[1]:
            try:
                remove_def(ops.git(clone, "show", f"{tip}:{loc[0]}"), loc[1])
            except Protected as exc:
                out.setdefault("protected", []).append({"id": u["id"], "note": str(exc)})
                continue
            except (ValueError, RuntimeError):
                pass
        if uncovered:
            out["unique"].append({"id": u["id"], "uncovered": uncovered, "covered": covered,
                                  "action": "convert to e2e first: no e2e test goes red on " + ", ".join(uncovered)})
        else:
            out["redundant"].append({"id": u["id"], "covered": covered})
    return out


def gate2(data: dict, clone: Path, wt: Path, tip: str, e2e: list[dict], extra: list[dict], cov_file: str | None) -> dict:
    changed = ops.git(clone, "diff", "--name-only", "--no-renames", "--diff-filter=AM", data["base"], data["head"]).split()
    cands = []
    for path in changed:
        if config.secret(CFG, path):
            continue
        if path.endswith(".py") and not is_test(path):
            cands += functions(path, ops.git(clone, "show", f"{tip}:{path}"))
    for x in extra:
        text = ops.git(clone, "show", f"{tip}:{x['path']}")
        match = [f for f in functions(x["path"], text) if f["name"] == x.get("name")]
        cands += [{**(match[0] if match else {"path": x["path"], "name": x.get("name"), "lines": []}),
                   "source": x.get("source", "guess tier"), "why": x.get("why", "")}]
    seen, uniq = set(), []
    for cd in cands:
        if (cd["path"], cd["name"]) not in seen:
            seen.add((cd["path"], cd["name"]))
            uniq.append(cd)
    if cov_file:
        hits = {p: set(v) for p, v in json.loads(Path(cov_file).read_text()).items()}
    else:
        hits: dict[str, set[int]] = {}
        with worktree(clone, wt, tip, "trim-coverage") as root:
            run_control.prepare(root, data)
            cov = Path(tempfile.mkdtemp(prefix="understando-cov-"))
            env = {"PYTHONPATH": os.pathsep.join([str(COV_SITE)] + ([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else [])),
                   "UNDERSTANDO_COV_ROOT": str(root), "UNDERSTANDO_COV_DIR": str(cov)}
            for e in e2e:
                run(root, e, env)
            for f in cov.glob("*.json"):
                for p, lines in json.loads(f.read_text()).items():
                    hits.setdefault(p, set()).update(lines)
            subprocess.run(["rm", "-rf", str(cov)])
    out = {"deletable": [], "needed": [], "excess_or_untested": [], "protected": []}
    for cd in uniq:
        item = {"path": cd["path"], "name": cd["name"], "source": cd["source"], **({"why": cd["why"]} if cd.get("why") else {})}
        owner = config.protected(CFG, cd["path"])
        if owner:
            out["protected"].append({**item, "note": f"a protected path (owner {owner.get('owner')}): report it, never delete it"})
            continue
        if not cd["lines"] or not hits.get(cd["path"], set()) & set(cd["lines"]):
            out["excess_or_untested"].append({**item, "note": "no e2e test runs it: excess, or untested. The user decides."})
            continue
        with worktree(clone, wt, tip, "trim-del") as root:
            run_control.prepare(root, data)
            f = root / cd["path"]
            try:
                f.write_text(remove_def(f.read_text(), cd["name"]))
            except Protected as exc:
                out["protected"].append({**item, "note": str(exc)})
                continue
            states = [run(root, e) for e in e2e]
        (out["deletable"] if all(s == "green" for s in states) else out["needed"]).append(item)
    return out


def key(item: dict) -> str:
    return f"{item['path']}:{item['name']}" if item.get("name") else item["path"]


def main(c: context.Ctx, argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="understando trim", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true", help="find, write trim.json, change nothing")
    ap.add_argument("--candidates")
    ap.add_argument("--coverage")
    ap.add_argument("--accept")
    ap.add_argument("--reason")
    args = ap.parse_args(argv)
    data, repo = c.need_map(), c.need_repo()
    out_path = c.run / "trim.json"
    if args.accept:
        if not args.reason:
            tm.fail("trim --accept needs --reason", 2)
        prev = json.loads(out_path.read_text()) if out_path.is_file() else {}
        prev.setdefault("accepted", {})[args.accept] = args.reason
        out_path.write_text(json.dumps(prev, indent=2) + "\n")
        journal.append(c.journal, "decision", f"trim: keep {args.accept}", repo, why=args.reason)
        context.emit(c, prev, f"accepted {args.accept}: {args.reason}")
        return 0
    verdicts.apply(data)
    global CFG
    import ci
    import repoinfo
    CFG = config.load(repoinfo.repo_name(repo))
    config.drop_inherited_key(CFG)
    refusal, _ = ci.gate(c, data)
    if refusal:
        print(refusal)
        return 1
    if not args.report:
        import review
        bad = [b for b in review.guard(c.run, [], CFG)]
        if bad:
            print("\n".join(bad))
            return 1
    e2e = [v for v in data["verifiers"] if v["kind"] in E2E_KINDS and "command" in v and v.get("state") not in DEAD]
    if not e2e:
        tm.fail("trim: no e2e verifier with a command; write one first (understando close, option 4)", 1)
    extra = json.loads(Path(args.candidates).read_text()) if args.candidates else []
    prev = json.loads(out_path.read_text()) if out_path.is_file() else {}
    with ops.scratch_clone(repo) as (clone, wt):
        ref = f"refs/remotes/origin/{ops.ready_branch(data)}"
        found = subprocess.run(["git", "-C", str(clone), "rev-parse", "-q", "--verify", ref], capture_output=True, text=True)
        branch_tip = found.stdout.strip() if found.returncode == 0 else data["head"]
        g3 = gate3(data, clone, wt, branch_tip, e2e)
        g2 = gate2(data, clone, wt, branch_tip, e2e, extra, args.coverage)
        deleted3, deleted2 = [], []
        if not args.report and (g3["redundant"] or g2["deletable"]):
            ops.ready_tip(repo, data)
            units = {v["id"]: v for v in data["verifiers"]}

            def change(root: Path) -> None:
                for r in g3["redundant"]:
                    loc = location(units[r["id"]], root)
                    if not loc:
                        raise ValueError(f"cannot find the test of {r['id']}; give it a `test` field")
                    path, name = loc
                    f = root / path
                    if name:
                        f.write_text(remove_def(f.read_text(), name))
                    else:
                        f.unlink()
                    deleted3.append({"id": r["id"], "path": path, "name": name})
                for item in g2["deletable"]:
                    f = root / item["path"]
                    f.write_text(remove_def(f.read_text(), item["name"]))
                    deleted2.append(item)

            names = ", ".join([r["id"] for r in g3["redundant"]] + [key(i) for i in g2["deletable"]])
            commit = ops.commit_on_ready(clone, wt, branch_tip, f"understando trim: delete {names}", change)
            moved = set()
            for r in g3["redundant"]:
                u = units[r["id"]]
                for kid, reds in r["covered"].items():
                    k = next(x for x in data["controls"] if x["id"] == kid)
                    target = next(v for v in data["verifiers"] if v["id"] == reds[0])
                    target["claims"] = list(dict.fromkeys(target["claims"] + u["claims"]))
                    k["verifier"] = target["id"]
                    k["expect"] = {"status": "red"}
                    k.pop("result", None)
                    moved.add(kid)
                data["verifiers"] = [v for v in data["verifiers"] if v["id"] != u["id"]]
            for v in data["verifiers"]:
                if v.get("at"):
                    v["at"] = commit
            for v in e2e:
                v["at"] = commit
            ops.probe(data, clone, wt, {v["id"] for v in e2e}, moved)
            bad = [v["id"] for v in e2e if (v.get("baseline") or {}).get("status") != "green"]
            if bad:
                tm.fail(f"trim: the e2e suite is not green after the deletions ({', '.join(bad)}); nothing was published", 1)
            ops.publish(clone, data, commit)
            tm.save(data, c.map)
    result = {"head": data["head"], "tip": (data.get("ready") or {}).get("head", data["head"]), "ran_at": tm.now(),
              "gate2": {**g2, "deleted": deleted2}, "gate3": {**g3, "deleted": deleted3},
              "accepted": prev.get("accepted", {}), "report_only": args.report}
    if deleted2:
        result["gate2"]["deletable"] = []
    if deleted3:
        result["gate3"]["redundant"] = []
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    lines = ["gate 3, unit tests:"]
    lines += [f"  deleted {d['id']} ({d['path']}{':' + d['name'] if d['name'] else ''}): an e2e test catches each of its controls" for d in deleted3]
    lines += [f"  redundant {r['id']}: deletable (report only)" for r in result["gate3"]["redundant"]]
    lines += [f"  keep {u['id']}: {u['action']}" for u in g3["unique"]]
    lines += [f"  checks nothing {x['id']}: {x['why']}" for x in g3["checks_nothing"]]
    lines.append("gate 2, excess code:")
    lines += [f"  deleted {key(d)}" for d in deleted2]
    lines += [f"  deletable {key(d)}: the e2e suite stays green without it (report only)" for d in result["gate2"]["deletable"]]
    lines += [f"  excess or untested {key(d)}" + (" (accepted: " + result["accepted"][key(d)] + ")" if key(d) in result["accepted"] else ": the user decides")
              for d in g2["excess_or_untested"]]
    lines += [f"  protected {key(d)}: {d['note']}" for d in g2["protected"]]
    lines += [f"  protected {d['id']}: {d['note']}" for d in g3.get("protected", [])]
    import routes
    cleanup = [r for r in routes.resolve_all() if r["skill"] in ("simplify", "ultra-clean", "deslop", "no-comments")]
    present = [r["skill"] for r in cleanup if r["use"] == "original"]
    lines.append("next: run " + (", ".join(present) if present else "the built-in pass (this one): probe-proven deletion plus a dead-code tool")
                 + " on the ready branch. Keep each @cc contract comment.")
    journal.append(c.journal, "result", f"trim deleted {len(deleted3)} unit tests and {len(deleted2)} functions.", repo,
                   why="Each deleted unit test has an e2e test that catches its controls.",
                   evidence=str(out_path),
                   result=f"{len(g3['unique'])} unit tests wait for conversion. {len(g2['excess_or_untested'])} parts need a user decision.")
    context.emit(c, result, "\n".join(lines))
    return 0
