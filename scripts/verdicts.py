#!/usr/bin/env python3
"""Apply the four-verdict rules to a trust map, deterministically.

    python3 scripts/verdicts.py trust-map.json            # write state, flags, verdicts, summary
    python3 scripts/verdicts.py trust-map.json --check    # exit 1 when the stored verdicts differ

The rules live in references/verdicts.md. This file is their only implementation.
Input: the inventory (claims, verifiers, controls) plus the baseline and control results.
Output: verifier `state`, the `flags` list, claim `verdict` and `reason`, and `summary`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tm  # noqa: E402

ORDER = ["Formal", "Proven", "Backed", "Asserted", "Gap"]


def control_outcome(control: dict) -> str:
    """caught | missed | error | not-run"""
    result = control.get("result")
    if not result or result["status"] == "skipped":
        return "not-run"
    if result["status"] == "red":
        return "caught" if result.get("matched", True) is not False else "error"
    if result["status"] == "green":
        return "missed"
    return "error"


def verifier_state(v: dict, controls: list[dict], flags: list[dict]) -> str:
    def flag(name: str, detail: str, loud: bool = False) -> None:
        flags.append({"flag": name, "subject": v["id"], "loud": loud, "detail": detail})

    if v["kind"] == "none":
        return "absent"  # a placeholder: no tool checks the claim
    if (v.get("import") or {}).get("status") == "stale":
        flag("stale-import", f"{v['id']}: the imported evidence failed its format check or changed: {v['import'].get('detail', '')}")
        return "stale"
    ind = v["independence"]
    if ind["by"] == "model":
        if ind.get("context") != "fresh":
            flag("shared-context", f"{v['id']} saw the PR context. It is one opinion counted twice.")

    if "mechanical" in v:
        result = v["mechanical"].get("result")
        if not result:
            flag("baseline-not-run", f"{v['id']} is a mechanical check that did not run. Run scripts/mechanical.py.")
            return "untested"
        if result["status"] == "fail":
            flag("fails-at-head", f"{v['id']} failed at the PR head: {result['detail'].splitlines()[0]}", loud=True)
            return "failing"
        return "checked"

    if "command" not in v:
        # A recorded proof or model can still show that it fails: a control result from a past run.
        if any(control_outcome(k) == "caught" for k in controls if (k.get("result") or {}).get("recorded")):
            return "proven"
        return "recorded"

    baseline = v.get("baseline")
    if not baseline or baseline["status"] == "skipped":
        flag("baseline-not-run", f"{v['id']} did not run at the PR head.")
        base_ok = None
    elif baseline["status"] == "green":
        base_ok = True
    elif baseline["status"] == "red":
        flag("fails-at-head", f"{v['id']} is red at the PR head without a control.", loud=True)
        return "failing"
    else:
        flag("baseline-error", f"{v['id']} did not complete at the PR head.", loud=True)
        return "broken"

    outcomes = [(k, control_outcome(k)) for k in controls]
    caught = [k for k, o in outcomes if o == "caught"]
    missed = [k for k, o in outcomes if o == "missed"]
    for k, o in outcomes:
        if o == "error":
            flag("control-error", f"Control {k['id']} on {v['id']} did not give a clean red or green.")
    if caught and base_ok:
        for k in missed:
            flag("control-missed", f"{v['id']} stayed green on control {k['id']}. It does not see that defect.")
        return "proven"
    if missed:
        ids = ", ".join(k["id"] for k in missed)
        flag("cannot-fail", f"{v['id']} stayed green on control {ids}. It checks nothing that the control broke.", loud=True)
        return "cannot-fail"
    return "untested"


def families(text: str | None) -> set[str]:
    """`openai, anthropic` -> {openai, anthropic}: a verifier can use more than one family."""
    return {f for f in re.split(r"[\s,+]+", text or "") if f}


def conformant(v: dict) -> bool:
    """A rung 4 or 5 check counts only with a passing conformance link to the real code. A check
    from a formal sidecar record counts only when the record itself rates Formal."""
    if (tm.ladder(v) or 0) < 4:
        return True
    record = v.get("formal_record")
    if record and (record.get("formal") or {}).get("verdict") != "Formal":
        return False
    return ((v.get("formal") or {}).get("conformance") or {}).get("status") == "pass"


def disagreeing(data: dict, inv_id: str | None) -> dict | None:
    """A user-confirmed invariant that the code at the head does not obey: a possible bug."""
    return next((i for i in data.get("invariants", []) if i["id"] == inv_id and i["author"] == "user"
                 and i["status"] == "accepted" and i.get("possible_bug")), None)


def user_confirmed(data: dict, inv_id: str | None) -> bool:
    """Proven and Formal need intent: a stated claim, or a link to an invariant that the user confirmed."""
    return any(i["id"] == inv_id and i["author"] == "user" and i["status"] == "accepted" for i in data.get("invariants", []))


def can_prove(v: dict, author_family: str | None) -> bool:
    if not conformant(v):
        return False
    if v["tier"] == "fact":
        return True
    ind = v["independence"]
    return (
        ind["by"] == "model"
        and ind.get("context") == "fresh"
        and bool(families(ind.get("family")))
        and author_family not in families(ind.get("family"))
    )


def apply(data: dict) -> dict:
    flags: list[dict] = []
    controls_by_verifier: dict[str, list[dict]] = {}
    for k in data["controls"]:
        controls_by_verifier.setdefault(k["verifier"], []).append(k)
    author = data.get("author_family")
    for v in data["verifiers"]:
        v["state"] = verifier_state(v, controls_by_verifier.get(v["id"], []), flags)
        if (v.get("user_path") or {}).get("result") == "internal-only":
            flags.append({"flag": "not-user-path", "subject": v["id"], "loud": True,
                          "detail": f"{v['id']} is labelled e2e, but it only calls internal functions: not a user-path e2e. "
                                    "Its tier label is integration. Drive the real CLI, service or UI to make it e2e."})
        ind = v["independence"]
        if ind["by"] == "model" and author and author in families(ind.get("family")):
            flags.append({
                "flag": "same-family", "subject": v["id"], "loud": False,
                "detail": f"{v['id']} uses the {author} family, the same family as the author.",
            })

    summary = {name: 0 for name in ORDER}
    import onto
    for c in data["claims"]:
        backing = [v for v in onto.checks_of(data, c) if onto.is_tool(v)]
        proven = [v for v in backing if v["state"] == "proven" and can_prove(v, author)]
        counted = [v for v in backing if v["state"] in ("proven", "untested", "recorded", "checked")]
        dead = [v for v in backing if v["state"] in ("cannot-fail", "failing", "broken", "stale")]
        rungs = [tm.ladder(v) for v in proven if tm.ladder(v)]
        # The tier is the strongest rung that a planted bug proved; the verdict is the weakest check.
        c["tier"] = max(rungs) if rungs else None
        weak, strength = onto.weakest_check(data, c)
        c["verdict"], c["reason"] = strength or ("Asserted" if c["stated"] else "Gap"), ""
        if c["verdict"] in ("Formal", "Proven"):
            ks = [k["id"] for k in controls_by_verifier.get(weak["id"], []) if control_outcome(k) == "caught"]
            if c["verdict"] == "Formal":
                link = weak["formal"]["conformance"]
                c["reason"] = (f"{weak['id']} is a rung {tm.ladder(weak)} {weak['formal']['tool']} check. Its conformance link "
                               f"({link['source']}) passes, and control {', '.join(ks)} broke it.")
            else:
                c["reason"] = f"{weak['id']} went red on control {', '.join(ks)}."
            if len(backing) > 1:
                c["reason"] += f" It is the weakest of the {len(backing)} checks."
        elif c["verdict"] == "Backed" and not [v for v in counted if v not in proven and onto.check_strength(data, v, c) == "Backed"]:
            ks = [k["id"] for k in controls_by_verifier.get(weak["id"], []) if control_outcome(k) == "caught"]
            c["reason"] = (f"{weak['id']} went red on control {', '.join(ks)}. It stays Backed: the PR does not state it, and it links to no "
                           "invariant that the user confirmed (understando discover).")
        elif c["verdict"] == "Backed":
            weak_ones = [v for v in counted if v not in proven and onto.check_strength(data, v, c) == "Backed"]
            ids = ", ".join(v["id"] for v in weak_ones)
            kinds = sorted({v["state"] for v in weak_ones})
            why = {
                "untested": "no control went red",
                "recorded": "the evidence is recorded, not run again",
                "checked": "it is a mechanical check (a grep or a line count) with no control",
                "proven": "a model verifier from the author family went red, or a proof has no passing conformance link",
            }
            c["reason"] = f"{ids} backs this claim, but " + " and ".join(why[s] for s in kinds) + "."
            pending = [v for v in weak_ones if v.get("formal_record") and (v["formal_record"].get("formal") or {}).get("verdict") != "Formal"]
            if pending and not [v for v in weak_ones if v not in pending]:
                c["reason"] = " ".join(f"{v['id']} backs this claim, but its formal record is {v['formal_record']['formal']['verdict']}."
                                       for v in pending)
            if proven and not onto.intent(data, c):
                c["reason"] += " A proven check cannot lift it: the PR does not state it, and it links to no invariant that the user confirmed."
        elif c["stated"]:
            c["reason"] = "Only the PR text states this claim."
        else:
            c["reason"] = "No verifier backs this claim, and the PR text does not state it."
        bug = next((b for b in (disagreeing(data, i) for i in onto.invariants_of(c)) if b), None)
        if bug:
            c["verdict"], c["tier"] = "Gap", None
            c["reason"] = (f"code disagrees with the confirmed invariant {bug['id']}"
                           + (f"; fix pending on {bug['fix_branch']}" if bug.get("fix_branch") else "; fix pending"))
        if dead and c["verdict"] not in ("Formal", "Proven"):
            c["reason"] += " " + " ".join(f"{v['id']} is {v['state']}." for v in dead)
        summary[c["verdict"]] += 1

    data["flags"] = flags
    data["summary"] = summary
    return data


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        tm.fail(__doc__.strip())
    path, check = argv[0], "--check" in argv
    data = tm.load(path)
    errors = tm.validate(data)
    if errors:
        tm.fail("invalid trust map:\n" + "\n".join(errors), 1)
    before = {c["id"]: c.get("verdict") for c in data["claims"]}
    apply(data)
    if check:
        diff = [cid for cid, old in before.items()
                if old != next(c["verdict"] for c in data["claims"] if c["id"] == cid)]
        if diff:
            print("verdicts differ: " + ", ".join(diff))
            return 1
        print("verdicts match")
        return 0
    tm.save(data, path)
    for c in data["claims"]:
        print(f"{c['id']:<5} {c['verdict']:<9} {c['text']}")
    print("summary: " + ", ".join(f"{k} {v}" for k, v in data["summary"].items()))
    for f in data["flags"]:
        if f.get("loud"):
            print(f"FLAG {f['flag'].upper()}: {f['detail']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
