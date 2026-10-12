"""understando discover: the user states the invariants of a feature, through edge-case questions.

    understando discover [--feature F] [--paths P ...]   mine candidates, then print the status
    understando discover questions                       the edge-case questions of each open candidate
    understando discover answer --answers FILE           record the user's decisions as invariants
    understando discover status                          DONE when every candidate has a decision
    understando discover import --sidecar FILE           the proposed invariants of a formal sidecar

1. mine: candidates from the code at the head (guards, asserts, early returns, isinstance
   narrowing, the result of a short function) in the paths of the feature, with evidence from the
   tests, the controls and git history. Each candidate is one plain line with its evidence. The
   candidates go to $R/discover.json.
2. questions: one to three "what should happen if" questions for each candidate: a boundary
   input, an odd event order, a failure part-way through. A question holds no answer.
3. answer: the user's answers define the invariant. An invariant is `author: user` only when the
   answer has "confirmed": true, which the agent writes only after the user said yes to the exact
   text. Else it is `author: agent`, status proposed. An example answer that the code at the head
   does not give is a possible bug, in the finding format of references/adapted/find-bugs.md.

The answer file: {"answers": [{"candidate": "D1", "decision": "accept|reword|reject|defer",
  "text"?: the user's statement, "reason"?: (reject, defer), "confirmed"?: true, "risky"?: true,
  "examples"?: [{"question", "expr", "expect" | "raises"}], "shape"?: "rule|process|wiring|input-space|flow",
  "rating"?: {"priority", "fix", "finding_confidence", "fix_confidence", "fix_direction"}}],
  "rest"?: {"decision": "defer", "reason": text}}
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import coderef  # noqa: E402
import ops  # noqa: E402
import store  # noqa: E402
import strength  # noqa: E402
from store import git  # noqa: E402

DECISIONS = ("accept", "reword", "reject", "defer")


def is_test(path: str) -> bool:
    parts = path.split("/")
    return any(p in ("tests", "test", "spec", "__tests__") for p in parts[:-1]) or parts[-1].startswith("test_")


def plain(node: ast.AST) -> str:
    return ast.unparse(node).replace("\n", " ")


def mine_python(path: str, source: str) -> list[dict]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        params = [a.arg for a in fn.args.args if a.arg not in ("self", "cls")]
        calls = {plain(c.func) for c in ast.walk(fn) if isinstance(c, ast.Call)}
        calls = {x for x in calls if not re.search(r"(Error|Exception)$", x)}
        pure = not (calls - {"isinstance", "len", "int", "str", "abs", "min", "max", "round", "float", "bool"})
        base = {"path": path, "function": fn.name, "start": fn.lineno, "end": fn.end_lineno, "params": params, "pure": pure}
        for node in ast.walk(fn):
            if isinstance(node, ast.If) and node.body:
                first = node.body[0]
                narrow = any(isinstance(c, ast.Call) and plain(c.func) == "isinstance" for c in ast.walk(node.test))
                if isinstance(first, ast.Raise):
                    exc = plain(first.exc.func if isinstance(first.exc, ast.Call) else first.exc) if first.exc else "an error"
                    text, kind = f"{fn.name}: when {plain(node.test)}, it raises {exc}.", "guard"
                elif isinstance(first, ast.Return):
                    text, kind = f"{fn.name}: when {plain(node.test)}, it returns early.", "early-return"
                elif narrow:
                    text, kind = f"{fn.name}: it narrows a value with {plain(node.test)}.", "narrowing"
                else:
                    continue
                out.append({**base, "kind": kind, "text": text, "line": node.lineno, "test": plain(node.test)})
            elif isinstance(node, ast.Assert):
                out.append({**base, "kind": "assert", "text": f"{fn.name}: {plain(node.test)} holds.", "line": node.lineno, "test": plain(node.test)})
        returns = [n for n in fn.body if isinstance(n, ast.Return) and n.value is not None]
        if returns and not isinstance(returns[-1].value, ast.Constant):
            r = returns[-1]
            out.append({**base, "kind": "result", "text": f"{fn.name} returns {plain(r.value)}.", "line": r.lineno})
    return out


def evidence(repo: Path, head: str, cand: dict, tests: dict[str, str]) -> list[str]:
    ev = [f"{cand['path']}:{cand['line']}"]
    for path, text in tests.items():
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(rf"\b{re.escape(cand['function'])}\b", line):
                ev.append(f"test {path}:{i}")
                break
    for line in git(repo, "log", "--format=%h %s", "-S", cand["function"], head, "--", cand["path"], check=False).splitlines()[:2]:
        ev.append(f"commit {line}")
    for line in git(repo, "log", "-i", "--grep=fix", "--format=%h %s", head, "--", cand["path"], check=False).splitlines()[:2]:
        ev.append(f"fix commit {line}")
    return list(dict.fromkeys(ev))


def questions(cand: dict) -> list[str]:
    """One to three "what should happen if" questions. Each names an edge; none gives the answer."""
    qs = []
    m = re.match(r"(\w+)\s*(>=|<=|>|<|==|!=)\s*(\w+)", cand.get("test", ""))
    if m:
        a, _, b = m.groups()
        qs += [f"What should happen if {a} is exactly equal to {b}?", f"What should happen if {a} is zero, or below zero?"]
    params = cand.get("params") or []
    if cand.get("kind") == "result" and params:
        qs += [f"What should {cand['function']} give when {params[0]} is zero?",
               f"What should {cand['function']} give when {params[0]} is below zero, or very large?"]
    if not cand.get("pure", True) and len(qs) < 3:
        qs.append(f"What should happen if a call inside {cand['function']} fails part-way through?")
    if cand.get("kind") == "formal" and cand.get("questions"):
        return cand["questions"][:3]
    if not qs:
        qs.append(f"What should happen if {cand.get('function', 'this code')} gets an input at the edge of its range?")
    return qs[:3]


def shape_of(cand: dict) -> str:
    if cand.get("record_kind"):
        return {"lean": "rule", "tla": "process", "property": "input-space"}.get(cand["record_kind"], "rule")
    if cand["kind"] == "narrowing":
        return "wiring"
    if cand["kind"] == "result":
        return "input-space"
    return "rule" if cand.get("pure") else "process"


def state_path(run: Path) -> Path:
    return run / "discover.json"


def load_state(run: Path) -> dict:
    p = state_path(run)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"candidates": [], "decisions": {}}


def save_state(run: Path, state: dict) -> None:
    state_path(run).write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def mine(c: store.Ctx, feature: str | None, paths: list[str]) -> dict:
    repo = c.need_repo()
    data = c.open_data()
    head = store.git(repo, "rev-parse", "HEAD")
    feat = store.find(data, "features", feature) if feature else None
    if feature and not feat:
        store.fail(f"discover: no feature {feature}. Run `understando create` first, or name --paths only.", 2)
    paths = paths or (feat or {}).get("paths") or []
    files = git(repo, "ls-tree", "-r", "--name-only", head, check=False).split()
    sources = [p for p in files if p.endswith(".py") and not is_test(p) and (not paths or any(p.startswith(x) for x in paths))]
    tests = {p: coderef.show(repo, head, p) or "" for p in files if is_test(p) and p.endswith(".py")}
    old = load_state(c.run)
    by_text = {cd["text"]: cd["id"] for cd in old["candidates"]}
    used = set(by_text.values())
    out = [cd for cd in old["candidates"] if cd.get("kind") == "formal"]
    n = 0
    for path in sources:
        for cand in mine_python(path, coderef.show(repo, head, path) or ""):
            cand["evidence"] = evidence(repo, head, cand, tests)
            cand["feature"] = feature
            cid = by_text.get(cand["text"])
            if not cid:
                while f"D{n + 1}" in used:
                    n += 1
                n += 1
                cid = f"D{n}"
                used.add(cid)
            cand["id"] = cid
            cand["questions"] = questions(cand)
            out.append(cand)
    state = {"head": head, "feature": feature, "candidates": out, "decisions": old.get("decisions", {})}
    save_state(c.run, state)
    if not c.store.is_file():
        c.save(data)
    return state


def import_sidecar(c: store.Ctx, path: str) -> dict:
    """Each proposed invariant of a formal sidecar becomes a candidate, with its questions."""
    side = json.loads(Path(path).read_text(encoding="utf-8"))
    state = load_state(c.run)
    have = {cd["id"] for cd in state["candidates"]}
    added = []
    for rec in side.get("verifiers", []):
        for item in (rec.get("invariant") or {}).get("items", []):
            qs = item.get("questions", [])
            ev = [f"record {rec['id']} ({rec['kind']}, tier {rec.get('ladder_tier')})"]
            ev += [f"{q['where']}: code today: {q['code_today']}" for q in qs if q.get("where")]
            cand = {"id": item["id"], "kind": "formal", "record": rec["id"], "record_kind": rec["kind"], "text": item["sentence"],
                    "evidence": ev, "questions": [q["ask"] for q in qs][:3], "feature": item.get("feature")}
            state["candidates"] = [cd for cd in state["candidates"] if cd["id"] != cand["id"]] + [cand]
            if cand["id"] not in have:
                added.append(cand["id"])
    save_state(c.run, state)
    return {"added": added, **status(c)}


def check_examples(repo: Path, head: str, cand: dict, examples: list[dict]) -> list[dict]:
    """Run each example answer against the code at the head. A different result is a possible bug."""
    if not examples or not cand.get("path", "").endswith(".py"):
        return []
    module = cand["path"][:-3].replace("/", ".")
    bugs = []
    with ops.scratch_clone(repo) as (clone, wt):
        root = wt / "discover"
        git(clone, "worktree", "add", "-q", "--detach", str(root), head)
        try:
            for ex in examples:
                code = (f"import sys; sys.path.insert(0, '.')\nfrom {module} import *\n"
                        f"try:\n    print(repr({ex['expr']}))\nexcept Exception as e:\n    print('raises ' + type(e).__name__)\n")
                out = subprocess.run([sys.executable, "-I", "-c", code], cwd=root, capture_output=True, text=True, timeout=60)
                got = out.stdout.strip() or (out.stderr.strip().splitlines() or [""])[-1]
                want = f"raises {ex['raises']}" if "raises" in ex else str(ex["expect"])
                if got != want:
                    bugs.append({"question": ex.get("question", ex["expr"]), "expr": ex["expr"], "expected": want, "got": got, "at_commit": head})
        finally:
            git(clone, "worktree", "remove", "--force", str(root))
    return bugs


def finding(inv: dict, bug: dict, rating: dict | None) -> list[str]:
    """The finding format of references/adapted/find-bugs.md."""
    r = rating or {}
    head = (f"{r.get('priority', 'P?')} — [{r.get('fix', 'not rated')}, {r.get('finding_confidence', 'not rated')} finding confidence, "
            f"{r.get('fix_confidence', 'not rated')} fix confidence] {inv['text']}")
    kind = "bug" if inv["author"] == "user" else "lead (the invariant is not the user's yet)"
    return [head, f"  Trigger: {bug['expr']}", f"  Expected: {bug['expected']}. Actual: {bug['got']}.",
            f"  Fix: {r.get('fix_direction', 'not rated')}", f"  Evidence: the example run at {bug['at_commit'][:10]} ({kind})"]


def answer(c: store.Ctx, path: str) -> dict:
    repo = c.need_repo()
    data = c.open_data()
    state = load_state(c.run)
    if not state["candidates"]:
        store.fail("discover answer: no candidates; run `understando discover` first", 2)
    cands = {cd["id"]: cd for cd in state["candidates"]}
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    answers = list(spec.get("answers", []))
    given = {a["candidate"] for a in answers}
    if spec.get("rest"):
        answers += [{**spec["rest"], "candidate": cid} for cid in cands if cid not in given and cid not in state["decisions"]]
    report = []
    for a in answers:
        cid, decision = a["candidate"], a.get("decision")
        if cid not in cands:
            store.fail(f"discover: no candidate {cid}", 2)
        if decision not in DECISIONS:
            store.fail(f"discover: {cid}: the decision is one of {', '.join(DECISIONS)}", 2)
        cand = cands[cid]
        inv = next((i for i in data["invariants"] if i.get("candidate") == cid), None)
        if decision in ("reject", "defer"):
            reason = a.get("reason") or ("deferred by the user" if decision == "defer" else None)
            if not reason:
                store.fail(f"discover: {cid}: a rejection needs a reason", 2)
            state["decisions"][cid] = {"decision": decision, "reason": reason, "at": store.now()}
            if inv:
                inv.update(status="rejected" if decision == "reject" else "deferred", reason=reason)
            report.append(f"{cid} {decision}: {reason}")
            continue
        text = a.get("text") or cand["text"]
        if decision == "reword" and not a.get("text"):
            store.fail(f"discover: {cid}: a reword needs the user's text", 2)
        import ste
        try:
            ste.require([text], f"discover: {cid}: the invariant text")
        except ste.SteMissing as exc:
            store.fail(str(exc), 1)
        except ValueError as exc:
            store.fail(f"{exc} Word the invariant again (decision reword).", 2)
        author = "user" if a.get("confirmed") is True else "agent"
        head = state.get("head") or store.git(repo, "rev-parse", "HEAD")
        bugs = check_examples(repo, head, cand, a.get("examples", []))
        shape = a.get("shape") or shape_of(cand)
        row = {"id": inv["id"] if inv else (cid if cand.get("kind") == "formal" else store.next_id(data, "invariants")),
               "text": text, "author": author, "status": "accepted" if author == "user" else "proposed",
               "candidate": cid, "evidence": cand.get("evidence", []), "shape": shape, "at": store.now(),
               **({"feature": cand["feature"]} if cand.get("feature") else {}),
               **({"risky": True} if a.get("risky") else {}),
               **({"examples": a["examples"]} if a.get("examples") else {}),
               **({"possible_bug": bugs} if bugs else {}),
               **({"code": [{"path": cand["path"], "symbol": cand["function"]}]} if cand.get("path") else {})}
        if inv:
            inv.clear()
            inv.update(row)
        else:
            data["invariants"].append(row)
        state["decisions"][cid] = {"decision": decision, "invariant": row["id"], "author": author, "at": store.now()}
        line = f"{cid} {decision} as {row['id']} ({row['status']}, author {author}, shape {shape}, suggested tier {store.LADDER[strength.SHAPE_KIND[shape]]}): {text}"
        if author != "user":
            line += " It is agent-picked: a claim on it stays Backed until the user accepts it."
        report.append(line)
        for b in bugs:
            report += finding(row, b, a.get("rating"))
    c.save(data)
    save_state(c.run, state)
    return {"report": report, **status(c)}


def status(c: store.Ctx) -> dict:
    state = load_state(c.run)
    open_ = [cd["id"] for cd in state["candidates"] if cd["id"] not in state["decisions"]]
    counts: dict[str, int] = {}
    for d in state["decisions"].values():
        counts[d["decision"]] = counts.get(d["decision"], 0) + 1
    data = c.data() or {"invariants": []}
    return {"candidates": len(state["candidates"]), "open": open_, "decisions": counts,
            "possible_bugs": [i["id"] for i in data["invariants"] if i.get("possible_bug")],
            "agent_picked": [i["id"] for i in data["invariants"] if i["author"] == "agent" and i["status"] == "proposed"],
            "done": bool(state["candidates"]) and not open_}


def status_text(s: dict) -> str:
    lines = [f"discover: {s['candidates']} candidates, {len(s['open'])} open; " + ", ".join(f"{v} {k}" for k, v in sorted(s["decisions"].items()))]
    if s["possible_bugs"]:
        lines.append("possible bugs: " + ", ".join(s["possible_bugs"]))
    if s["agent_picked"]:
        lines.append("agent-picked, not accepted by the user: " + ", ".join(s["agent_picked"]))
    lines.append("DONE: every candidate has a decision." if s["done"] else "OPEN: " + ", ".join(s["open"][:12]) + (" ..." if len(s["open"]) > 12 else ""))
    return "\n".join(lines)


def main(c: store.Ctx, argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="understando discover", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", nargs="?", default="mine", choices=["mine", "questions", "answer", "status", "import"])
    ap.add_argument("--feature")
    ap.add_argument("--paths", nargs="*", default=[])
    ap.add_argument("--answers")
    ap.add_argument("--sidecar")
    args = ap.parse_args(argv)
    c.need_run()
    if args.action == "mine":
        mine(c, args.feature, args.paths)
        s = status(c)
        store.emit(c, s, status_text(s))
    elif args.action == "questions":
        state = load_state(c.run)
        rows = [{"id": cd["id"], "text": cd["text"], "evidence": cd.get("evidence", []), "questions": cd.get("questions", [])}
                for cd in state["candidates"] if cd["id"] not in state["decisions"]]
        text = "\n".join(f"{r['id']}  {r['text']}\n    evidence: {', '.join(r['evidence'])}\n" + "\n".join(f"    - {q}" for q in r["questions"]) for r in rows)
        store.emit(c, {"open": rows}, text or "No open candidate.")
    elif args.action == "import":
        if not args.sidecar:
            store.fail("discover import: pass --sidecar FILE", 2)
        out = import_sidecar(c, args.sidecar)
        store.emit(c, out, f"imported {len(out['added'])} candidates: {', '.join(out['added'])}\n" + status_text(out))
    elif args.action == "answer":
        if not args.answers:
            store.fail("discover answer: pass --answers FILE", 2)
        out = answer(c, args.answers)
        store.emit(c, out, "\n".join(out["report"]) + "\n" + status_text(out))
    else:
        s = status(c)
        store.emit(c, s, status_text(s))
    return 0
