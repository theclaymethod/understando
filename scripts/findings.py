"""The finding format of every bug that understando reports (adapted from agent-guards find-bugs, MIT).

    P1 — [Small fix, 95% finding confidence, 90% fix confidence] <one line>
      Trigger: <the input or edge case>
      Expected: <what the contract says>. Actual: <what the code does>.
      Impact: <what goes wrong for a user or the system>
      Fix: <the fix direction that the fix estimates refer to>
      Evidence: <the run, test or witness that shows it> (ref: ...)

discover (an answer that the code contradicts), the code-first route of formalize, close and the
review findings all use it. A finding is `verified` when its execution path and its contract
support it (a confirmed invariant plus a run that shows the other result). Else it is a `lead`.
Leads are listed apart from bugs. A rating that nobody gave shows as "not rated", never as an
invented number.
"""

from __future__ import annotations

DASH = "—"


def heading(f: dict) -> str:
    r = f.get("rating") or {}
    pri = r.get("priority") or "P2"
    fix = f"{r['fix']} fix" if r.get("fix") else "fix size not rated"
    fc = f"{r['finding_confidence']}% finding confidence" if r.get("finding_confidence") is not None else "finding confidence not rated"
    xc = f"{r['fix_confidence']}% fix confidence" if r.get("fix_confidence") is not None else "fix confidence not rated"
    return f"{pri} {DASH} [{fix}, {fc}, {xc}] {f['line']}"


def render(f: dict, indent: str = "  ") -> list[str]:
    out = [heading(f)]
    r = f.get("rating") or {}
    if f.get("trigger"):
        out.append(f"{indent}Trigger: {f['trigger']}")
    if f.get("expected") or f.get("actual"):
        out.append(f"{indent}Expected: {f.get('expected', 'not stated')}. Actual: {f.get('actual', 'not observed')}.")
    if f.get("impact") or r.get("impact"):
        out.append(f"{indent}Impact: {f.get('impact') or r['impact']}")
    if r.get("fix_direction") or f.get("fix"):
        out.append(f"{indent}Fix: {r.get('fix_direction') or f['fix']}")
    if f.get("fixed"):
        out.append(f"{indent}Status: {f['fixed']}")
    if f.get("evidence"):
        out.append(f"{indent}Evidence: {f['evidence']}" + (f" (ref: {f['ref']})" if f.get("ref") else ""))
    return out


def from_possible_bug(inv: dict, bug: dict, confirmed: bool, fixed: str | None = None) -> dict:
    """A discover or formalize possible bug as a finding."""
    r = bug.get("rating") or {}
    status = r.get("status") or ("verified" if confirmed and bug.get("got") else "lead")
    return {"status": status, "rating": r,
            "line": f"{(inv.get('name') or inv.get('text', '')).rstrip('.')}: the code does not do this",
            "trigger": bug.get("question", "").rstrip("?") + "?" if bug.get("question") else None,
            "expected": bug.get("expected"), "actual": bug.get("got"),
            "evidence": "the user's confirmed answer, and a run of the code that gives the other result" if confirmed
                        else "an answer that the user did not confirm", "fixed": fixed,
            "ref": ", ".join(x for x in [inv.get("id"), bug.get("where")] if x)}


def collect(data: dict, fixed: dict[str, str] | None = None) -> list[dict]:
    """Each possible bug in the trust map as a finding; `fixed` maps an invariant ID to a status line."""
    out = []
    for inv in data.get("invariants", []):
        confirmed = inv.get("author") == "user" and inv.get("status") == "accepted"
        for b in inv.get("possible_bug") or []:
            out.append(from_possible_bug(inv, b, confirmed, (fixed or {}).get(inv["id"])))
    return out


def report(items: list[dict]) -> list[str]:
    """Verified bugs first, then the leads, each block under its own heading."""
    bugs = [f for f in items if f["status"] == "verified"]
    leads = [f for f in items if f["status"] != "verified"]
    key = lambda f: ((f.get("rating") or {}).get("priority") or "P2")  # noqa: E731
    out = []
    if bugs:
        out.append(f"Bugs found ({len(bugs)}):")
        for f in sorted(bugs, key=key):
            out += render(f)
    if leads:
        out.append(f"Leads, not verified ({len(leads)}):")
        for f in sorted(leads, key=key):
            out += render(f)
    return out
