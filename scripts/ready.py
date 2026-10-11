"""understando ready: run map, probe, close, trim and explain, then print the four-gate checklist.

    understando ready --report             gates only, from the current data (the agent may run it)
    understando ready [--answers FILE]     the full run (the user starts it)
    understando ready --cold-read          also name the optional paid cold read; it never runs here

The gates:
  1 verified     each claim is Formal, Proven or Backed, or the user waived it
  2 no excess    trim found no deletable code, and the user decided each "excess or untested" item
  3 no doubles   trim found no unit test that an e2e test already covers
  4 explainable  explain.py builds (glossary, level rules), each claim is in one promise, and the
                 STE lint of the PR section has 0 hard violations

The checklist goes to $R/ready.json. explain puts it at the top of the explainer and of
pr-section.md. Gate details are plain text with no ID; the IDs are in each gate's items.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ctx as context  # noqa: E402
import journal  # noqa: E402
import tm  # noqa: E402
import verdicts  # noqa: E402

S = Path(__file__).resolve().parent
CLOSED = ("Formal", "Proven", "Backed")
def review_route() -> str:
    """The independent review: an installed original, else the adapted code-review copy."""
    import routes
    rows = {r["skill"]: r for r in routes.resolve_all()}
    present = [n for n in ("interrogate", "nemesis-review", "code-review") if rows.get(n, {}).get("use") == "original"]
    where = ("the skill " + " or ".join(present)) if present else "references/adapted/code-review.md, with a model of a different family in a fresh context"
    return f"Independent review: run {where}. The user starts it."
COLD = ("Cold read (optional, paid): a model of a different family reads the explainer in a fresh context. "
        "Show the cost and wait for a clear yes. understando makes no model call.")


def ste_lint() -> str | None:
    for base in (Path.home() / ".agents/skills/asd-ste100", Path.home() / ".claude/skills/asd-ste100"):
        if (base / "scripts/ste-lint.py").is_file():
            return str(base / "scripts/ste-lint.py")
    return None


def lint_hard(path: Path) -> tuple[int | None, str]:
    lint = ste_lint()
    if not lint:
        return None, "the STE lint (asd-ste100) is not installed"
    out = subprocess.run([sys.executable, "-I", lint, str(path)], capture_output=True, text=True)
    m = re.search(r"\((\d+) hard", out.stdout)
    return (int(m.group(1)) if m else None), out.stdout.strip().splitlines()[-2] if out.stdout.strip() else out.stderr.strip()


def gate4(c: context.Ctx, data: dict) -> dict:
    errors = tm.validate(data)
    items = list(errors)
    with tempfile.TemporaryDirectory(prefix="understando-ready-") as tmp:
        argv = [sys.executable, str(S / "explain.py"), "--map", str(c.map), "--repo", str(c.need_repo()), "--out", tmp]
        if (c.run / "explain.json").is_file():
            argv += ["--extra", str(c.run / "explain.json")]
        out = subprocess.run(argv, capture_output=True, text=True)
        built = out.returncode == 0
        if not built:
            items.append("explain.py: " + (out.stderr.strip().splitlines() or ["failed"])[-1][:300])
            hard = None
        else:
            hard, line = lint_hard(Path(tmp) / "pr-section.md")
            items.append(f"STE lint of the PR section: {line}")
    ok = built and not errors and hard == 0
    detail = ("The explainer builds, each claim is in one promise, and the plain-English check finds no hard error."
              if ok else "The explainer does not build, a claim is not in one promise, or the plain-English check finds a hard error.")
    return {"n": 4, "name": "explainable", "pass": ok, "detail": detail, "items": items}


def gates(c: context.Ctx, data: dict) -> list[dict]:
    claims = data["claims"]
    open_ = [x for x in claims if x.get("verdict") not in CLOSED and not x.get("waiver")]
    waived = [x for x in claims if x.get("waiver") and x.get("verdict") not in CLOSED]
    g1 = {"n": 1, "name": "verified", "pass": not open_,
          "detail": f"{len(claims) - len(open_) - len(waived)} of {len(claims)} claims are verified" + (f", and the user waived {len(waived)}" if waived else "") + (f". {len(open_)} are open." if open_ else "."),
          "items": [f"{x['id']} is {x['verdict']}: {x['text']}" for x in open_] + [f"{x['id']} waived: {x['waiver']['reason']}" for x in waived]}
    trim_path = c.run / "trim.json"
    trim = json.loads(trim_path.read_text()) if trim_path.is_file() else None
    if not trim or trim.get("head") != data["head"]:
        g2 = {"n": 2, "name": "no excess code", "pass": False, "detail": "The trim step did not run at this head.", "items": ["run: understando trim"]}
        g3 = {"n": 3, "name": "no unit test that an e2e test covers", "pass": False, "detail": "The trim step did not run at this head.", "items": ["run: understando trim"]}
    else:
        accepted = trim.get("accepted", {})
        key = lambda d: f"{d['path']}:{d['name']}" if d.get("name") else d["path"]  # noqa: E731
        undecided = [d for d in trim["gate2"]["excess_or_untested"] if key(d) not in accepted]
        deletable = trim["gate2"]["deletable"]
        g2 = {"n": 2, "name": "no excess code", "pass": not undecided and not deletable,
              "detail": (f"{len(deletable)} parts can go, and {len(undecided)} parts that no end-to-end test runs need a decision."
                         if undecided or deletable else "No code can go, and the user decided each part that no end-to-end test runs."),
              "items": [f"deletable {key(d)}" for d in deletable] + [f"excess or untested {key(d)}" for d in undecided]
              + [f"kept {k}: {v}" for k, v in accepted.items()] + [f"deleted {key(d)}" for d in trim["gate2"].get("deleted", [])]}
        red = trim["gate3"]["redundant"]
        g3 = {"n": 3, "name": "no unit test that an e2e test covers", "pass": not red,
              "detail": (f"{len(red)} unit tests repeat an end-to-end test." if red else "No unit test repeats an end-to-end test."),
              "items": [f"redundant {r['id']}" for r in red] + [f"deleted {d['id']}" for d in trim["gate3"].get("deleted", [])]
              + [f"keep {u['id']}: {u['action']}" for u in trim["gate3"]["unique"]]}
    return [g1, g2, g3, gate4(c, data)]


def checklist(result: dict) -> str:
    lines = [f"ready: {'PASS' if result['pass'] else 'FAIL'} at {result['head'][:10]}"]
    for g in result["gates"]:
        lines.append(f"[{'x' if g['pass'] else ' '}] gate {g['n']} {g['name']}: {'pass' if g['pass'] else 'fail'}. {g['detail']}")
        lines += [f"      {i}" for i in g.get("items", [])]
    lines.append(review_route())
    if result.get("cold_read"):
        lines.append(COLD)
    return "\n".join(lines)


def main(c: context.Ctx, argv: list[str], run_verb) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="understando ready", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--answers")
    ap.add_argument("--cold-read", action="store_true")
    args = ap.parse_args(argv)
    data = c.need_map()
    c.need_repo()
    if not args.report:
        for verb, extra in (("map", []), ("probe", []), ("close", ["--answers", args.answers] if args.answers else ["--list"]),
                            ("trim", []), ("explain", [])):
            print(f"\n== ready: {verb}")
            code = run_verb(verb, extra)
            if code:
                print(f"ready: {verb} exited {code}; the gates below use the data as it is")
        data = c.need_map()
    verdicts.apply(data)
    result = {"head": data["head"], "at": tm.now(), "gates": gates(c, data), "cold_read": args.cold_read}
    result["pass"] = all(g["pass"] for g in result["gates"])
    (c.run / "ready.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    if not args.report:
        print("\n== ready: explain with the checklist")
        run_verb("explain", [])
    journal.append(c.journal, "result", "ready: " + ", ".join(f"gate {g['n']} {'pass' if g['pass'] else 'fail'}" for g in result["gates"]), c.repo)
    context.emit(c, result, checklist(result))
    return 0
