"""understando close: close each Asserted or Gap claim, riskiest first, with the user.

    understando close --list                 the queue, riskiest first, with the seven options
    understando close --answers FILE         apply the user's answers (the agent asks, then writes the file)
    understando close                        on a terminal: ask each question here

The seven options for each claim:
  1 mechanical   a grep or a line count (scripts/mechanical.py)        -> Backed
  2 formalize    tier 4 or 5; route to `understando formalize`          -> stays open
  3 property     a property test or a contract, drafted by the agent    -> Proven when probe sees red
  4 e2e          an e2e test, drafted by the agent                      -> Proven when probe sees red
  5 evidence     attach recorded evidence                               -> Backed
  6 reword       reword the claim, or drop it
  7 waive        waive with a reason: the checklist and the PR body show it

A drafted test goes into a scratch worktree of a private clone. probe runs it at that commit,
first green, then with the planted bug. Only when it goes red with the expected pattern does the
commit go to understando/<pr>-ready in the reviewed repo. A check for a claim that the PR does
not state needs a user-confirmed invariant (understando discover); close refuses it otherwise.

Answer file: {"answers": [{"claim": "C03", "choice": "e2e", "invariant"?: "I01",
  "files": {path: text}, "verifier": {"description", "command": {"argv": [...]}, "kind"?, "test"?},
  "control": {"description", "recipe"?, "edits": [...], "expect": {"status": "red", "pattern"}}},
  {"claim": "C04", "choice": "waive", "reason": "..."},
  {"claim": "C02", "choice": "mechanical", "check": {"op", "pattern", "paths"}, "description"},
  {"claim": ..., "choice": "evidence", "recorded": {"source", "result", "at"?}, "description"},
  {"claim": ..., "choice": "reword", "text": "...", "plain"?: {...}} or {"choice": "drop"}]}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ctx as context  # noqa: E402
import journal  # noqa: E402
import mechanical  # noqa: E402
import ops  # noqa: E402
import tm  # noqa: E402
import verdicts  # noqa: E402

OPTIONS = [("mechanical", "a mechanical check: a grep or a line count"),
           ("formalize", "formalize it: a TLA+ model check or a Lean proof (tier 4 or 5)"),
           ("property", "a property test or a contract"),
           ("e2e", "an e2e test"),
           ("evidence", "attach recorded evidence (Backed)"),
           ("reword", "reword the claim, or drop it"),
           ("waive", "waive it with a reason")]
CLOSED = ("Formal", "Proven", "Backed")


def risk(c: dict, loud: set[str], data: dict) -> tuple:
    """Gap before Asserted; a claim with a loud flag on its verifier first; then the ID."""
    flagged = any(c["id"] in v["claims"] and v["id"] in loud for v in data["verifiers"])
    return (0 if c["verdict"] == "Gap" else 1, 0 if flagged else 1, c["id"])


def queue(data: dict) -> list[dict]:
    loud = {f["subject"] for f in data.get("flags", []) if f.get("loud")}
    open_ = [c for c in data["claims"] if c.get("verdict") not in CLOSED and not c.get("waiver")]
    return sorted(open_, key=lambda c: risk(c, loud, data))


def add_check(c: context.Ctx, data: dict, claim: dict, a: dict, kind: str) -> str:
    refusal = ops.intent_ok(data, claim, a.get("invariant"))
    if refusal:
        return refusal
    if a.get("invariant"):
        claim["invariant"] = a["invariant"]
    repo = c.need_repo()
    import config
    import repoinfo
    import review
    bad = review.guard(c.run, sorted(a.get("files", {})), config.load(repoinfo.repo_name(repo)))
    if bad:
        return f"{claim['id']}: " + " ".join(bad) + " Nothing went to the ready branch."
    import ci
    prof = ci.load(c.run)
    cmd = a["verifier"]["command"]
    if prof and not ci.allowed_by(prof, cmd["argv"], cmd.get("cwd", ".")):
        return (f"{claim['id']}: refuse: the drafted command `{' '.join(cmd['argv'])}` is not in the approved CI profile. "
                "Use a command of the repo's reviewed CI. Nothing went to the ready branch.")
    vid, kid = ops.next_id(data, "V"), ops.next_id(data, "K")
    spec = a["verifier"]
    v = {"id": vid, "kind": spec.get("kind", kind), "claims": [claim["id"]], "tier": "fact",
         "description": spec["description"], "command": spec["command"],
         "independence": {"by": "tool", "tool": spec["command"]["argv"][0]}, "cost": {"usd": 0},
         "provenance": f"Drafted by understando close on {ops.ready_branch(data)}, with the user."}
    if spec.get("test"):
        v["test"] = spec["test"]
    k = {"id": kid, "verifier": vid, "recipe": a["control"].get("recipe", "plant-violation"),
         "description": a["control"]["description"], "edits": a["control"]["edits"], "expect": a["control"]["expect"]}
    with ops.scratch_clone(repo) as (clone, wt):
        tip = ops.ready_tip(repo, data)

        def write(root: Path) -> None:
            for rel, text in a["files"].items():
                dest = (root / rel).resolve()
                if not dest.is_relative_to(root.resolve()):
                    raise ValueError(f"{rel} leaves the worktree")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(text, encoding="utf-8")

        commit = ops.commit_on_ready(clone, wt, tip, f"understando close: {kind} check for {claim['id']}", write)
        v["at"] = commit
        trial = json.loads(json.dumps(data))
        trial["verifiers"].append(v)
        trial["controls"].append(k)
        ops.probe(trial, clone, wt, {vid}, {kid})
        tv = next(x for x in trial["verifiers"] if x["id"] == vid)
        tk = next(x for x in trial["controls"] if x["id"] == kid)
        if tv["state"] != "proven":
            base = (tv.get("baseline") or {}).get("status")
            got = (tk.get("result") or {}).get("status")
            return (f"{claim['id']}: the new {kind} check did not prove itself (baseline {base}, control {got}). "
                    "Nothing went to the ready branch. Fix the draft and answer again.")
        ops.publish(clone, data, commit)
    data["verifiers"].append(tv)
    data["controls"].append(tk)
    verdicts.apply(data)
    return f"{claim['id']}: {vid} goes green, and red on control {kid}. Commit {commit[:10]} is on {ops.ready_branch(data)}."


def apply_answer(c: context.Ctx, data: dict, a: dict) -> str:
    claim = next((x for x in data["claims"] if x["id"] == a["claim"]), None)
    if not claim:
        tm.fail(f"close: no claim {a['claim']}", 2)
    choice = a["choice"]
    if choice in ("mechanical", "1"):
        vid = ops.next_id(data, "V")
        data["verifiers"].append({"id": vid, "kind": "boundary", "claims": [claim["id"]], "tier": "fact",
                                  "description": a["description"], "mechanical": a["check"],
                                  "independence": {"by": "tool", "tool": "git grep"}, "cost": {"usd": 0},
                                  "provenance": "Added by understando close; scripts/mechanical.py runs it at the PR head."})
        v = data["verifiers"][-1]
        v["mechanical"]["result"] = {**mechanical.run(str(c.need_repo()), data["base"], data["head"], v["mechanical"]), "ran_at": tm.now()}
        verdicts.apply(data)
        return f"{claim['id']}: mechanical check {vid} is {v['mechanical']['result']['status']}; the claim is {claim['verdict']}."
    if choice in ("formalize", "2"):
        refusal = ops.intent_ok(data, claim, a.get("invariant"))
        if refusal:
            return refusal
        claim["tier_target"] = a.get("tier", 5)
        return f"{claim['id']}: route to `understando formalize --claim {claim['id']}` (user-invoked). It stays open."
    if choice in ("property", "3"):
        return add_check(c, data, claim, a, "property")
    if choice in ("e2e", "4"):
        return add_check(c, data, claim, a, "e2e")
    if choice in ("evidence", "5"):
        vid = ops.next_id(data, "V")
        data["verifiers"].append({"id": vid, "kind": a.get("kind", "measurement"), "claims": [claim["id"]], "tier": "fact",
                                  "description": a["description"], "recorded": a["recorded"],
                                  "independence": {"by": "tool", "tool": a.get("tool", "recorded run")}, "cost": {"usd": 0},
                                  "provenance": a.get("provenance", "Recorded by understando close from the user's evidence.")})
        verdicts.apply(data)
        return f"{claim['id']}: recorded evidence {vid}; the claim is {claim['verdict']}."
    if choice in ("reword", "drop", "6"):
        if choice == "drop" or a.get("drop"):
            data["claims"] = [x for x in data["claims"] if x["id"] != claim["id"]]
            for p in data.get("promises", []):
                p["claims"] = [x for x in p["claims"] if x != claim["id"]]
            data["promises"] = [p for p in data.get("promises", []) if p["claims"]]
            for v in data["verifiers"]:
                v["claims"] = [x for x in v["claims"] if x != claim["id"]]
            verdicts.apply(data)
            return f"{claim['id']}: dropped."
        claim["text"] = a["text"]
        if a.get("plain"):
            claim["plain"] = a["plain"]
        verdicts.apply(data)
        return f"{claim['id']}: reworded; it is {claim['verdict']}. Run probe if a check now fits."
    if choice in ("waive", "7"):
        if not a.get("reason"):
            tm.fail(f"close: {claim['id']}: a waiver needs a reason", 2)
        claim["waiver"] = {"reason": a["reason"], "at": tm.now()}
        return f"{claim['id']}: waived. Reason: {a['reason']}"
    tm.fail(f"close: unknown choice {choice!r}", 2)
    return ""


def kind_of(choice: str) -> str:
    return {"1": "verifier-choice", "2": "verifier-choice", "3": "verifier-choice", "4": "verifier-choice",
            "5": "verifier-choice", "waive": "waiver", "7": "waiver"}.get(choice, "decision" if choice in ("reword", "drop", "6") else "verifier-choice")


def ask(data: dict) -> list[dict]:
    """The terminal path: one question per claim. A drafted test comes from a JSON file."""
    answers = []
    for claim in queue(data):
        print(f"\n{claim['id']} ({claim['verdict']}): {claim['text']}\n  {claim.get('reason', '')}")
        for i, (name, line) in enumerate(OPTIONS, 1):
            print(f"  {i}. {line}")
        pick = input("choose 1-7, or press Enter to skip: ").strip()
        if not pick:
            continue
        choice = OPTIONS[int(pick) - 1][0]
        a = {"claim": claim["id"], "choice": choice}
        if choice == "waive":
            a["reason"] = input("reason: ").strip()
        elif choice == "reword":
            a["text"] = input("new text (or 'drop'): ").strip()
            if a["text"] == "drop":
                a = {"claim": claim["id"], "choice": "drop"}
        elif choice != "formalize":
            a.update(json.loads(Path(input("path of the JSON answer with the draft: ").strip()).read_text()))
        answers.append(a)
    return answers


def main(c: context.Ctx, argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="understando close", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--answers")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)
    data = c.need_map()
    verdicts.apply(data)
    if args.answers and c.repo:
        import ci
        refusal, _ = ci.gate(c, data)
        if refusal:
            print(refusal)
            return 1
    if args.list or (not args.answers and not sys.stdin.isatty()):
        q = queue(data)
        rows = [{"claim": x["id"], "verdict": x["verdict"], "text": x["text"], "options": [n for n, _ in OPTIONS]} for x in q]
        text = "\n".join(f"{x['id']} {x['verdict']}: {x['text']}" for x in q) or "Every claim is Formal, Proven, Backed or waived."
        context.emit(c, {"queue": rows, "options": OPTIONS}, text + ("\noptions: " + "; ".join(f"{i}. {l}" for i, (_, l) in enumerate(OPTIONS, 1)) if q else ""))
        return 0
    answers = json.loads(Path(args.answers).read_text())["answers"] if args.answers else ask(data)
    order = {x["id"]: i for i, x in enumerate(queue(data))}
    report = []
    for a in sorted(answers, key=lambda a: order.get(a["claim"], 99)):
        line = apply_answer(c, data, a)
        tm.save(data, c.map)
        report.append(line)
        journal.append(c.journal, kind_of(a["choice"]), f"close {a['claim']}: {a['choice']}", c.repo,
                       why=a.get("reason") or a.get("why"), result=line, claims=[a["claim"]])
    left = queue(data)
    report.append("DONE: every claim is Formal, Proven, Backed or waived." if not left else
                  "OPEN: " + ", ".join(f"{x['id']} {x['verdict']}" for x in left))
    context.emit(c, {"report": report, "open": [x["id"] for x in left]}, "\n".join(report))
    return 0
