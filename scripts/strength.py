"""The strength of each check, part and claim, and the evidence bar of its feature. The rules live
in references/verdicts.md and references/evidence-bars.md; this file is their only implementation.

- A check is proven when it is green at the head and a control (a planted bug, a stub, a mutant or
  a degraded variant) made it fail. A check that stayed green on each of its controls cannot fail:
  it does not count.
- A rung 4 or 5 check (TLA+, Lean) counts only with a passing conformance link to the real code,
  and only when its formal record rates Formal.
- A part is as strong as its strongest proven check. A claim is as strong as its weakest part.
- Proven and Formal need intent: each invariant of the claim is the user's (author user,
  accepted). A claim on an agent-picked invariant stays Backed, and the report says so.
- The bar of the feature's surface: frontend, a real-browser e2e with a video and screenshots;
  backend, Formal for a risky claim, else a property test, types, a contract or an import rule;
  llm, an eval with a frozen judge or labels and a degraded variant that scored worse; other, any
  proven check.

    python3 scripts/strength.py verify.json     print the strengths
"""

from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import store  # noqa: E402

ORDER = ["Formal", "Proven", "Backed", "Gap"]
VIDEO = ("*.webm", "*.mp4", "*.mov")
SHOT = ("*.png", "*.jpg", "*.jpeg")


def score_of(check: dict, result: dict | None) -> float | None:
    if not result:
        return None
    if result.get("score") is not None:
        return result["score"]
    pat = (check.get("eval") or {}).get("score")
    m = re.search(pat, result.get("output_tail") or "", re.M) if pat else None
    return float(m.group(1)) if m else None


def outcome(check: dict, k: dict) -> str:
    """caught | missed | error | not-run"""
    r = k.get("result")
    if not r or r["status"] == "skipped":
        return "not-run"
    if k["kind"] == "degraded":
        base, got = score_of(check, check.get("baseline")), score_of(check, r)
        if r["status"] == "red":
            return "caught"
        if base is None or got is None:
            return "error"
        worse = got < base if (check.get("eval") or {}).get("better", "higher") == "higher" else got > base
        return "caught" if worse else "missed"
    if r["status"] == "red":
        return "caught" if r.get("matched") is not False else "error"
    return "missed" if r["status"] == "green" else "error"


def conformant(v: dict) -> bool:
    if (store.ladder(v) or 0) < 4:
        return True
    rec = v.get("formal_record")
    if rec and (rec.get("formal") or {}).get("verdict") != "Formal":
        return False
    return ((v.get("formal") or {}).get("conformance") or {}).get("status") == "pass"


def check_state(v: dict, controls: list[dict], flags: list[dict]) -> str:
    def flag(name: str, detail: str, loud: bool = False) -> None:
        flags.append({"flag": name, "subject": v["id"], "loud": loud, "detail": detail})

    outs = [(k, outcome(v, k)) for k in controls]
    caught = [k for k, o in outs if o == "caught"]
    missed = [k for k, o in outs if o == "missed"]
    for k, o in outs:
        if o == "error":
            flag("control-error", f"control {k['id']} on {v['id']} gave no clean result")
    if "command" not in v:
        if caught and conformant(v):
            return "proven"
        return "recorded"
    base = v.get("baseline")
    if not base or base["status"] == "skipped":
        flag("not-run", f"{v['id']} did not run at the head")
        return "untested" if not missed else "cannot-fail"
    if base["status"] == "red":
        flag("fails-at-head", f"{v['id']} is red at the head without a control", loud=True)
        return "failing"
    if base["status"] == "error":
        flag("error-at-head", f"{v['id']} did not complete at the head", loud=True)
        return "broken"
    if caught:
        for k in missed:
            flag("control-missed", f"{v['id']} stayed green on control {k['id']}: it does not see that bug")
        return "proven" if conformant(v) else "recorded"
    if missed:
        flag("cannot-fail", f"{v['id']} stayed green on each control ({', '.join(k['id'] for k in missed)}): it cannot fail, so it does not count", loud=True)
        return "cannot-fail"
    flag("no-control", f"{v['id']} has no control that ran: nothing shows that it can fail")
    return "untested"


def evidence_ok(v: dict) -> tuple[bool, str]:
    """frontend: the check asks for a video and a screenshot, and its last run left both."""
    want = (v.get("evidence") or {}).get("require") or []
    got = (v.get("baseline") or {}).get("evidence") or []
    has = lambda globs, files: any(fnmatch.fnmatch(Path(f).name, g) for f in files for g in globs)  # noqa: E731
    if not (has(VIDEO, want) and has(SHOT, want)):
        return False, "the e2e does not ask for a video and a screenshot (evidence.require)"
    if not (has(VIDEO, got) and has(SHOT, got)):
        return False, "the last run left no video and screenshot"
    return True, ""


def meets_bar(surface: str, risky: bool, v: dict, controls: list[dict]) -> tuple[bool, str]:
    """Does one proven check meet the bar of its surface?"""
    rung = store.ladder(v) or 0
    if surface == "frontend":
        if v["kind"] != "e2e":
            return False, "frontend needs a real-browser e2e"
        return evidence_ok(v)
    if surface == "backend":
        if risky:
            return (rung >= 4, "" if rung >= 4 else "a risky backend claim needs a Lean or TLA+ check with conformance")
        return (rung >= 2, "" if rung >= 2 else "backend needs a property test, types, a @cc contract or an import rule")
    if surface == "llm":
        if v["kind"] != "eval" or not (v.get("eval") or {}).get("frozen"):
            return False, "llm needs a recorded eval with a frozen judge or labels"
        if not any(k["kind"] == "degraded" and outcome(v, k) == "caught" for k in controls):
            return False, "llm needs a degraded variant that scored worse"
        return True, ""
    return True, ""


def intent(data: dict, invs: list[str]) -> tuple[bool, list[str]]:
    """True when each invariant is the user's. The second value lists the agent-picked ones."""
    rows = [store.find(data, "invariants", i) for i in invs]
    agent = [i for i, r in zip(invs, rows) if not r or r["author"] != "user" or r["status"] != "accepted"]
    return bool(invs) and not agent, agent


def parts_of(cl: dict) -> list[dict]:
    return cl.get("parts") or [{"id": cl["id"], "text": cl["text"], "checks": cl.get("checks", []), "invariants": cl.get("invariants", [])}]


def apply(data: dict) -> dict:
    """Write each check's state, and return the derived report: the flags, each claim's strength and bar."""
    flags: list[dict] = []
    by_check: dict[str, list[dict]] = {}
    for k in data["controls"]:
        by_check.setdefault(k["check"], []).append(k)
    checks = {v["id"]: v for v in data["checks"]}
    for v in data["checks"]:
        v["state"] = check_state(v, by_check.get(v["id"], []), flags)
    claims = []
    summary = {name: 0 for name in ORDER}
    for cl in data["claims"]:
        feat = store.find(data, "features", cl.get("feature")) or {}
        surface = feat.get("surface", "other")
        risky = bool(cl.get("risky")) or any((store.find(data, "invariants", i) or {}).get("risky") for i in cl.get("invariants", []))
        rows = []
        for p in parts_of(cl):
            vs = [checks[x] for x in p.get("checks", []) if x in checks]
            proven = [v for v in vs if v["state"] == "proven"]
            ok, agent = intent(data, p.get("invariants") or cl.get("invariants", []))
            best = max(proven, key=lambda v: store.ladder(v) or 0, default=None)
            if best and ok:
                verdict = "Formal" if (store.ladder(best) or 0) >= 4 else "Proven"
            elif vs:
                verdict = "Backed"
            else:
                verdict = "Gap"
            bar = [meets_bar(surface, risky, v, by_check.get(v["id"], [])) for v in proven]
            met = any(b[0] for b in bar)
            why = "" if met else next((b[1] for b in bar if b[1]), "no check that a control proved")
            if best and not ok:
                why = (why + "; " if why else "") + f"agent-picked invariant {', '.join(agent) or '(none linked)'}: the user has not accepted it"
            rows.append({"part": p["id"], "verdict": verdict, "tier": store.ladder(best) if best else None,
                         "best": best["id"] if best else None, "bar_met": met, "why": why,
                         "dead": [v["id"] for v in vs if v["state"] in ("cannot-fail", "failing", "broken")]})
        weakest = max(rows, key=lambda r: (ORDER.index(r["verdict"]), -(r["tier"] or 0)))
        summary[weakest["verdict"]] += 1
        claims.append({"id": cl["id"], "feature": cl.get("feature"), "surface": surface, "risky": risky, "text": cl["text"],
                       "verdict": weakest["verdict"], "tier": weakest["tier"], "weakest_part": weakest["part"],
                       "bar_met": all(r["bar_met"] for r in rows), "why": weakest["why"], "parts": rows})
    return {"flags": flags, "claims": claims, "summary": summary}


def lines(report: dict) -> list[str]:
    out = []
    for c in report["claims"]:
        bar = "meets its bar" if c["bar_met"] else f"below its {c['surface']} bar"
        out.append(f"{c['id']:<4} {c['verdict']:<7} tier {c['tier'] or '-'}  {bar}: {c['text']}" + (f"  ({c['why']})" if c["why"] else ""))
    out.append("summary: " + ", ".join(f"{k} {v}" for k, v in report["summary"].items()))
    out += [f"FLAG {f['flag'].upper()}: {f['detail']}" for f in report["flags"] if f.get("loud")]
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        store.fail(__doc__.strip())
    d = store.load(sys.argv[1])
    print("\n".join(lines(apply(d))))
