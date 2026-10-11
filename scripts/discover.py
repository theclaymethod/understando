"""understando discover: find the invariants together with the user, before any verifier exists.

    understando discover [mine] [--paths P ...] [--claim C01]   mine candidates, then print status
    understando discover questions                             the edge-case questions for each open candidate
    understando discover answer --answers FILE                 record the user's decisions
    understando discover status                                done when every candidate has a decision
    understando discover import --sidecar FILE                 the proposed invariants of a formal sidecar

1. mine: candidates from the code at the head (guards, asserts, early returns, isinstance
   narrowing, the result of a short function), with evidence from the tests, the controls and git
   history (`git log -S`, fix commits); and from the PR text and the journal prompts. Each
   candidate is one plain line plus its evidence (file:line, commit). Written to $R/discover.json.
2. questions: one to three "what should happen if" questions per candidate, from boundary
   inputs, odd event orders and a failure part-way through. A question holds no answer.
3. answer: the user's answers define the invariant. A row is `author: user` only when the answer
   has "confirmed": true, which the agent writes only after the user said yes. An example answer
   that the code at the head does not give is a possible bug.
4. Each accepted invariant gets a suggested tier (rule 5, process 4, wiring 3, input space 2,
   flow 1) and a frog EV score: risk (1-3) times cost if wrong (1-3), divided by the effort to
   verify (1-3). Do the highest score first: eat the frog.

The answer file: {"answers": [{"candidate": "D01", "decision": "accept|reword|reject|defer",
  "text"?: the user's statement (reword), "reason"?: (reject, defer), "confirmed"?: true,
  "examples"?: [{"question", "expr", "expect" | "raises"}], "shape"?, "frog"?: {"risk", "impact",
  "effort"}, "claims"?: [claim id], "source_prompt"?: text}],
  "rest"?: {"decision": "defer", "reason": text}}
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coderef  # noqa: E402
import ctx as context  # noqa: E402
import journal  # noqa: E402
import ops  # noqa: E402
import tm  # noqa: E402

SHAPE_TIER = {"rule": 5, "process": 4, "wiring": 3, "input-space": 2, "flow": 1}
DECISIONS = ("accept", "reword", "reject", "defer")


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else ""


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
        kinds = {a.arg: plain(a.annotation) if a.annotation else "" for a in fn.args.args}
        calls = {plain(c.func) for c in ast.walk(fn) if isinstance(c, ast.Call)}
        calls = {x for x in calls if not re.search(r"(Error|Exception)$", x)}
        pure = not (calls - {"isinstance", "len", "int", "str", "abs", "min", "max", "round", "float", "bool"})
        params = [p for p in params if kinds.get(p) not in ("str", "bytes")] + [p for p in params if kinds.get(p) in ("str", "bytes")]
        guards = 0
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
                guards += 1
                out.append({"kind": kind, "text": text, "path": path, "line": node.lineno, "function": fn.name,
                            "end": fn.end_lineno, "start": fn.lineno, "params": params, "pure": pure,
                            "test": plain(node.test)})
            elif isinstance(node, ast.Assert):
                guards += 1
                out.append({"kind": "assert", "text": f"{fn.name}: {plain(node.test)} holds.", "path": path,
                            "line": node.lineno, "function": fn.name, "start": fn.lineno, "end": fn.end_lineno,
                            "params": params, "pure": pure, "test": plain(node.test)})
        returns = [n for n in fn.body if isinstance(n, ast.Return) and n.value is not None]
        if returns and not isinstance(returns[-1].value, ast.Constant):
            r = returns[-1]
            out.append({"kind": "result", "text": f"{fn.name} returns {plain(r.value)}.", "path": path, "line": r.lineno,
                        "function": fn.name, "start": fn.lineno, "end": fn.end_lineno, "params": params, "pure": pure})
    return out


def edit_hits(repo: Path, head: str, edit: dict, cand: dict, span: str) -> bool:
    """Does a control edit change this candidate? An anchor edit resolves with coderef at the head and
    is compared by its resolved lines (the match, else the whole symbol); a typed find by its text."""
    if edit.get("op") in coderef.ANCHOR_OPS:
        try:
            r = coderef.resolve(repo, head, coderef.anchor_ref(edit), cap=False)
        except coderef.AnchorError:
            return False
        if r.span:
            starts = coderef.line_starts(r.text)
            lo, hi = coderef.line_of(starts, r.span[0]), coderef.line_of(starts, max(r.span[0], r.span[1] - 1))
        else:
            lo = getattr(r.sym.node, "lineno", r.start) if r.sym else r.start
            hi = r.end
        return cand["start"] <= lo and hi <= cand["end"]
    return bool(edit.get("find") and edit["find"].strip() and edit["find"].strip() in span)


def evidence(repo: Path, data: dict, cand: dict, test_files: dict[str, str]) -> list[str]:
    ev = [f"{cand['path']}:{cand['line']}"]
    for path, text in test_files.items():
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(rf"\b{re.escape(cand['function'])}\b", line):
                ev.append(f"test {path}:{i}")
                break
    head_text = git(repo, "show", f"{data['head']}:{cand['path']}").splitlines()
    span = "\n".join(head_text[cand["start"] - 1:cand["end"]])
    for k in data.get("controls", []):
        if any(e["path"] == cand["path"] and edit_hits(repo, data["head"], e, cand, span) for e in k["edits"]):
            ev.append(f"control {k['id']}")
    for line in git(repo, "log", "--format=%h %s", "-S", cand["function"], data["head"], "--", cand["path"]).splitlines()[:2]:
        ev.append(f"commit {line}")
    for line in git(repo, "log", "-i", "--grep=fix", "--format=%h %s", data["head"], "--", cand["path"]).splitlines()[:2]:
        ev.append(f"fix commit {line}")
    return list(dict.fromkeys(ev))


def narrative(run: Path, data: dict) -> str:
    for p in (run / "pr-body.md", tm.ROOT / str(data.get("narrative", "")), run / str(data.get("narrative", ""))):
        if p.is_file():
            return p.read_text(encoding="utf-8")
    return ""


def mine(c: context.Ctx, paths: list[str], claim: str | None) -> dict:
    data, repo = c.need_map(), c.need_repo()
    changed = git(repo, "diff", "--name-only", "--no-renames", "--diff-filter=AM", data["base"], data["head"]).split()
    if claim:
        cl = next((x for x in data["claims"] if x["id"] == claim), None)
        if not cl:
            tm.fail(f"discover: no claim {claim}", 2)
        paths = paths + [r["path"] for r in cl.get("code", [])]
    import config
    cfg = config.for_repo(repo)
    changed = config.readable(cfg, changed)
    sources = [p for p in changed if p.endswith(".py") and not is_test(p) and (not paths or any(p.startswith(x) for x in paths))]
    tests = {p: git(repo, "show", f"{data['head']}:{p}") for p in config.readable(cfg, git(repo, "ls-tree", "-r", "--name-only", data["head"]).split()) if is_test(p)}
    found = []
    for path in sources:
        for cand in mine_python(path, git(repo, "show", f"{data['head']}:{path}")):
            cand["evidence"] = evidence(repo, data, cand, tests)
            cand["source"] = "code"
            found.append(cand)
    if not claim and not paths:
        for i, line in enumerate(narrative(c.run, data).splitlines(), 1):
            m = re.match(r"\s*[-*]\s+(.+)", line)
            if m:
                found.append({"kind": "pr", "source": "pr", "text": m.group(1).replace("`", ""), "evidence": [f"PR text line {i}"]})
        for row in journal.read(c.journal):
            if row.get("kind") == "prompt":
                found.append({"kind": "journal", "source": "journal", "text": journal.what(row), "evidence": [f"journal {row['ts']}"]})
    old = load(c.run)
    by_text = {cd["text"]: cd for cd in old.get("candidates", [])}
    out = []
    for i, cand in enumerate(found, 1):
        prev = by_text.get(cand["text"])
        cand["id"] = prev["id"] if prev else None
        out.append(cand)
    used = {cd["id"] for cd in out if cd["id"]}
    n = 0
    for cand in out:
        if not cand["id"]:
            while True:
                n += 1
                if f"D{n:02d}" not in used:
                    break
            cand["id"] = f"D{n:02d}"
            used.add(cand["id"])
        cand["questions"] = questions(cand)
    state = {"head": data["head"], "candidates": out, "decisions": old.get("decisions", {})}
    save(c.run, state)
    return state


def questions(cand: dict) -> list[str]:
    """One to three "what should happen if" questions. Each names an edge; none gives the answer."""
    qs = []
    test = cand.get("test", "")
    m = re.match(r"(\w+)\s*(>=|<=|>|<|==|!=)\s*(\w+)", test)
    if m:
        a, _, b = m.groups()
        qs.append(f"What should happen if {a} is exactly equal to {b}?")
        qs.append(f"What should happen if {a} is zero, or below zero?")
    params = cand.get("params") or []
    if cand.get("kind") == "result" and params:
        qs.append(f"What should {cand['function']} give when {params[0]} is zero?")
        qs.append(f"What should {cand['function']} give when {params[0]} is below zero, or very large?")
    if cand.get("kind") in ("pr", "journal"):
        qs += ["What should happen if the input is at the edge of its range, for example empty or zero?",
               "What should happen if two of these events arrive in the other order?",
               "What should happen if the run stops part-way through?"]
    if not cand.get("pure", True) and len(qs) < 3:
        qs.append(f"What should happen if a call inside {cand['function']} fails part-way through?")
    if not qs:
        qs.append(f"What should happen if {cand.get('function', 'this code')} gets an input at the edge of its range?")
    return qs[:3]


def load(run: Path) -> dict:
    p = run / "discover.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def save(run: Path, state: dict) -> None:
    run.mkdir(parents=True, exist_ok=True)
    (run / "discover.json").write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def import_sidecar(c: context.Ctx, path: str) -> dict:
    """Each proposed invariant of a formal sidecar becomes a candidate, with its edge-case questions
    and what the code does today as evidence. Each question that the pilot marked unclear becomes
    a candidate of its own (<item>-q<n>), so the user can answer or defer it alone."""
    side = json.loads(Path(path).read_text(encoding="utf-8"))
    state = load(c.run) or {"candidates": [], "decisions": {}}
    state.setdefault("decisions", {})
    have = {cd["id"] for cd in state["candidates"]}
    added = []
    for rec in side.get("verifiers", []):
        inv = rec.get("invariant") or {}
        for item in inv.get("items", []):
            qs = item.get("questions", [])
            ev = [f"record {rec['id']} ({rec['kind']}, tier {rec.get('ladder_tier')})"]
            ev += [f"checked by {', '.join(item['checked_by'])}"] if item.get("checked_by") else []
            ev += [f"{q['where']}: code today: {q['code_today']}" for q in qs if q.get("where")]
            cand = {"id": item["id"], "kind": "formal", "source": "formal", "record": rec["id"], "record_kind": rec["kind"], "claims": rec.get("claims", []),
                    "text": item["sentence"], "evidence": ev, "questions": [q["ask"] for q in qs][:3]}
            rows = [cand]
            for n, q in enumerate(qs, 1):
                if str(q.get("looks", "")).startswith("unclear"):
                    rows.append({"id": f"{item['id']}-q{n}", "kind": "question", "source": "formal", "record": rec["id"], "record_kind": rec["kind"],
                                 "parent": item["id"], "text": q["ask"], "questions": [q["ask"]],
                                 "evidence": [f"{q.get('where', '')}: code today: {q.get('code_today', '')}", f"the pilot: {q['looks']}"]})
            for r in rows:
                if r["id"] in have:
                    state["candidates"] = [r if cd["id"] == r["id"] else cd for cd in state["candidates"]]
                else:
                    state["candidates"].append(r)
                    have.add(r["id"])
                    added.append(r["id"])
    state["sidecar"] = str(Path(path).resolve())
    save(c.run, state)
    return {"added": added, **status(c)}


def check_examples(repo: Path, data: dict, cand: dict, examples: list[dict]) -> list[dict]:
    """Run each example answer against the code at the head. A different result is a possible bug."""
    if not examples or cand.get("source") != "code" or not cand["path"].endswith(".py"):
        return []
    module = cand["path"][:-3].replace("/", ".")
    bugs = []
    with ops.scratch_clone(repo) as (clone, wt):
        root = wt / "discover"
        ops.git(clone, "worktree", "add", "-q", "--detach", str(root), data["head"])
        try:
            for ex in examples:
                code = (f"import sys; sys.path.insert(0, '.')\nfrom {module} import *\n"
                        f"try:\n    print(repr({ex['expr']}))\nexcept Exception as e:\n    print('raises ' + type(e).__name__)\n")
                out = subprocess.run([sys.executable, "-I", "-c", code], cwd=root, capture_output=True, text=True, timeout=60)
                got = out.stdout.strip() or (out.stderr.strip().splitlines() or [""])[-1]
                want = f"raises {ex['raises']}" if "raises" in ex else str(ex["expect"])
                if got != want:
                    bugs.append({"question": ex.get("question", ex["expr"]), "expected": want, "got": got})
        finally:
            ops.git(clone, "worktree", "remove", "--force", str(root))
    return bugs


def shape_of(cand: dict) -> str:
    if cand.get("record_kind"):
        return {"lean": "rule", "tla": "process", "property": "input-space"}.get(cand["record_kind"], "rule")
    if cand.get("source") in ("pr", "journal"):
        return "flow"
    if cand["kind"] == "narrowing":
        return "wiring"
    if cand["kind"] == "result":
        return "input-space"
    return "rule" if cand.get("pure") else "process"


def answer(c: context.Ctx, path: str) -> dict:
    data, repo = c.need_map(), c.need_repo()
    state = load(c.run)
    if not state.get("candidates"):
        state = mine(c, [], None)
        data = c.need_map()
    cands = {cd["id"]: cd for cd in state["candidates"]}
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    answers = list(spec.get("answers", []))
    given = {a["candidate"] for a in answers}
    rest = spec.get("rest")
    if rest:
        answers += [{**rest, "candidate": cid} for cid in cands if cid not in given and cid not in state["decisions"]]
    data.setdefault("invariants", [])
    report = []
    for a in answers:
        cid, decision = a["candidate"], a.get("decision")
        if cid not in cands:
            tm.fail(f"discover: no candidate {cid}", 2)
        if decision not in DECISIONS:
            tm.fail(f"discover: {cid}: decision must be one of {', '.join(DECISIONS)}", 2)
        cand = cands[cid]
        if decision in ("reject", "defer"):
            reason = a.get("reason") or ("deferred by the user" if decision == "defer" else None)
            if not reason:
                tm.fail(f"discover: {cid}: a rejection needs a reason", 2)
            state["decisions"][cid] = {"decision": decision, "reason": reason, "at": tm.now(), **({"owner": a["owner"]} if a.get("owner") else {})}
            journal.append(c.journal, "invariant", cand["text"], repo, author="user", status="rejected" if decision == "reject" else "deferred",
                           candidate=cid, reason=reason, owner=a.get("owner"), flag=a.get("flag"), evidence=", ".join(cand["evidence"]))
            if cand.get("source") == "formal":
                row = {"id": cid, "text": cand["text"], "author": "agent", "status": "proposed" if decision == "defer" else "rejected",
                       "candidate": cid, "evidence": cand["evidence"], "reason": reason, "at": tm.now(), "record": cand["record"],
                       **({"deferred": True} if decision == "defer" else {}),
                       **{k: a[k] for k in ("owner", "flag") if a.get(k)}, **({"parent": cand["parent"]} if cand.get("parent") else {})}
                data["invariants"] = [i for i in data["invariants"] if i["id"] != cid] + [row]
            report.append(f"{cid} {decision}: {reason}" + (f" Owner: {a['owner']}." if a.get("owner") else "") + (f" FLAG: {a['flag']}." if a.get("flag") else ""))
            continue
        text = a.get("text") if decision == "reword" else (a.get("text") or cand["text"])
        if decision == "reword" and not a.get("text"):
            tm.fail(f"discover: {cid}: a reword needs the user's text", 2)
        import ste
        try:
            ste.require([text], f"discover: {cid}: the invariant text")
        except (ValueError, ste.SteMissing) as exc:
            tm.fail(f"{exc} Word the invariant again (decision reword).", 2)
        author = "user" if a.get("confirmed") is True else "agent"
        bugs = check_examples(repo, data, cand, a.get("examples", []))
        shape = a.get("shape") or shape_of(cand)
        frog = a.get("frog") or {}
        ev = round(frog.get("risk", 2) * frog.get("impact", 2) / max(frog.get("effort", 2), 1), 2)
        inv = next((i for i in data["invariants"] if i["candidate"] == cid), None)
        inv_id = inv["id"] if inv else (cid if cand.get("source") == "formal" else ops.next_id(data, "I"))
        bugs += [{"question": b["question"], "expected": b["expected"], "got": b["got"], **({"where": b["where"]} if b.get("where") else {})}
                 for b in a.get("possible_bug", [])]
        bugs = [{**b, "at_commit": data["head"], **({"rating": b.get("rating") or a["rating"]} if (b.get("rating") or a.get("rating")) else {})}
                for b in bugs]
        row = {"id": inv_id, "text": text, "author": author, "status": "accepted" if author == "user" else "proposed",
               "candidate": cid, "evidence": cand["evidence"], "tier": SHAPE_TIER[shape], "shape": shape, "frog_ev": ev,
               "at": tm.now(), **({"source_prompt": a["source_prompt"]} if a.get("source_prompt") else {}),
               **({"possible_bug": bugs} if bugs else {}),
               **{k: a[k] for k in ("route", "fix_branch", "flag", "owner") if a.get(k)},
               **({"record": cand["record"]} if cand.get("record") else {}),
               **({"parent": cand["parent"]} if cand.get("parent") else {})}
        if inv:
            inv.clear()
            inv.update(row)
        else:
            data["invariants"].append(row)
        for claim_id in a.get("claims", []):
            cl = next((x for x in data["claims"] if x["id"] == claim_id), None)
            if not cl:
                tm.fail(f"discover: {cid}: no claim {claim_id}", 2)
            cl["invariant"] = inv_id
            cl.setdefault("tier_target", SHAPE_TIER[shape])
        state["decisions"][cid] = {"decision": decision, "invariant": inv_id, "author": author, "at": tm.now()}
        journal.append(c.journal, "invariant", text, repo, author=author, status=row["status"], candidate=cid,
                       invariant=inv_id, claims=a.get("claims", []), source_prompt=a.get("source_prompt"),
                       evidence=", ".join(cand["evidence"]), tier=row["tier"], frog_ev=ev, possible_bug=bugs)
        line = f"{cid} {decision} as {inv_id} ({row['status']}, author {author}, tier {row['tier']} {shape}, frog EV {ev}): {text}"
        if author != "user":
            line += " PROPOSED: no user confirm, so no verifier may use it."
        report.append(line)
        import findings
        import names
        named = {**row, "name": names.short(text)}
        for b in bugs:
            report += findings.render(findings.from_possible_bug(named, b, author == "user"))
    tm.save(data, c.map)
    save(c.run, state)
    return {"report": report, **status(c)}


def status(c: context.Ctx) -> dict:
    state = load(c.run)
    cands = state.get("candidates", [])
    decided = state.get("decisions", {})
    open_ = [cd["id"] for cd in cands if cd["id"] not in decided]
    counts: dict[str, int] = {}
    for d in decided.values():
        counts[d["decision"]] = counts.get(d["decision"], 0) + 1
    data = c.data() or {}
    bugs = [f"{i['id']} ({i['candidate']})" for i in data.get("invariants", []) if i.get("possible_bug")]
    proposed = [i["id"] for i in data.get("invariants", []) if i["status"] == "proposed"]
    return {"candidates": len(cands), "open": open_, "decisions": counts, "possible_bugs": bugs,
            "proposed": proposed, "done": bool(cands) and not open_}


def status_text(s: dict) -> str:
    lines = [f"discover: {s['candidates']} candidates, {len(s['open'])} open; "
             + ", ".join(f"{v} {k}" for k, v in sorted(s["decisions"].items()))]
    if s["possible_bugs"]:
        lines.append("possible bugs: " + ", ".join(s["possible_bugs"]))
    if s["proposed"]:
        lines.append("proposed, not confirmed by the user: " + ", ".join(s["proposed"]))
    lines.append("DONE: every candidate has a decision." if s["done"] else
                 "OPEN: " + ", ".join(s["open"][:12]) + (" ..." if len(s["open"]) > 12 else ""))
    return "\n".join(lines)


def main(c: context.Ctx, argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="understando discover", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", nargs="?", default="mine", choices=["mine", "questions", "answer", "status", "import"])
    ap.add_argument("--sidecar")
    ap.add_argument("--answers")
    ap.add_argument("--paths", nargs="*", default=[])
    ap.add_argument("--claim")
    args = ap.parse_args(argv)
    if args.action == "mine":
        mine(c, args.paths, args.claim)
        s = status(c)
        context.emit(c, s, status_text(s))
    elif args.action == "questions":
        state = load(c.run) or mine(c, args.paths, args.claim)
        decided = state.get("decisions", {})
        rows = [{"id": cd["id"], "text": cd["text"], "evidence": cd["evidence"], "questions": cd["questions"]}
                for cd in state["candidates"] if cd["id"] not in decided]
        text = "\n".join(f"{r['id']}  {r['text']}\n    evidence: {', '.join(r['evidence'])}\n" + "\n".join(f"    - {q}" for q in r["questions"]) for r in rows)
        context.emit(c, {"open": rows}, text or "No open candidate.")
    elif args.action == "import":
        if not args.sidecar:
            tm.fail("discover import: pass --sidecar runs/<repo>/<pr>/formal/verifiers.json", 2)
        out = import_sidecar(c, args.sidecar)
        context.emit(c, out, f"imported {len(out['added'])} candidates: {', '.join(out['added'])}\n" + status_text(out))
    elif args.action == "answer":
        if not args.answers:
            tm.fail("discover answer: pass --answers FILE", 2)
        out = answer(c, args.answers)
        context.emit(c, out, "\n".join(out["report"]) + "\n" + status_text(out))
    else:
        s = status(c)
        context.emit(c, s, status_text(s))
    return 0
