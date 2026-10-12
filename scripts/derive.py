"""The derived block of refs.resolved.json: the values that visual-explainer renders and never computes
again (its card plugins/visual-explainer/cards/trust-map.md, "The data contract").

    derive.derived(data, rep, head, checks, controls, refs) -> {"schema": 2, "head", "claims", "verify", "checks"}

- claims[id]: strength, tier, the claim's checks with their result, "2 checks: 2 caught their bug.",
  the evidence of its weakest part with its action, the flagged checks, its parts, and its bar.
- verify: "4 of 5 checks caught their planted bug.", each check that cannot fail, and one "what we
  broke" sentence for each control.
- checks[id]: the result of each check, the claims it backs, its test ref and its controls.

The strength itself comes from strength.py (`rep`); this file words it. A check result is one of
caught, cannot-fail, broken, no-bug, recorded or none. The card also reads `verify.missed`, which
stays 0: a check that stayed green on one control and was caught by another is proven.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import store  # noqa: E402
import strength  # noqa: E402

BAR = {  # surface -> (level, need); a risky backend claim needs a proof
    "frontend": ("e2e", "a real-browser e2e with a video and screenshots"),
    "backend": ("property", "a property test, types, a contract or an import rule"),
    "llm": ("eval", "a recorded eval with a frozen judge and a degraded variant that scored worse"),
    "other": ("check", "a check that a planted bug proved"),
}
RISKY_BAR = ("formal", "a Lean or TLA+ proof that matches the code")
WORDS = {"caught": "caught their bug", "cannot-fail": "cannot fail", "no-bug": "had no planted bug",
         "recorded": "are records of a past run", "broken": "fail at the head"}
ONE = {"caught": "caught its bug", "cannot-fail": "cannot fail", "no-bug": "had no planted bug",
       "recorded": "is a record of a past run", "broken": "fails at the head"}
SAID = {"caught": "It caught its planted bug.", "cannot-fail": "It cannot fail: it passed on each planted bug.",
        "broken": "It fails or does not complete.", "no-bug": "No planted bug ran, so no run proved that it can fail.",
        "recorded": "It is a record of a past run, and we did not run it again.", "none": "No tool checks it."}
OP = {"delete-line": "We deleted the line", "invert-condition": "We inverted the condition", "replace-with": "We replaced the code",
      "drop-allowlist-row": "We deleted a row of an allowlist", "restore-file": "We restored the stub of", "corrupt-byte": "We changed one byte of",
      "delete-file": "We deleted the file"}


def listing(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def none_check(claim_id: str) -> dict:
    """The placeholder check of a claim that no tool checks (the card: a check of kind none)."""
    return {"id": f"{claim_id}-none", "name": "no check", "kind": "none"}


def result_of(v: dict) -> str:
    """The result of one check, from the state that strength.py wrote."""
    if v["kind"] == "none":
        return "none"
    return {"proven": "caught", "cannot-fail": "cannot-fail", "failing": "broken", "broken": "broken", "recorded": "recorded"}.get(v.get("state"), "no-bug")


def strength_of(v: dict) -> str:
    if v.get("state") != "proven":
        return "Gap" if v["kind"] == "none" else "Backed"
    return "Formal" if (store.ladder(v) or 0) >= 4 else "Proven"


def broke(k: dict) -> str:
    """What we broke, as one full short sentence: the description of the control, else its first edit."""
    text = (k.get("description") or "").strip()
    if text and not text.startswith("A planted bug from"):
        return text if text.endswith((".", "!", "?")) else text + "."
    e = (k.get("edits") or [{}])[0]
    where = f" in {e['symbol']}" if isinstance(e.get("symbol"), str) else (f" in {e['path']}" if e.get("path") else "")
    match = f" `{e['match']}`" if e.get("match") else ""
    return f"{OP.get(e.get('op'), 'We planted a bug')}{match}{where}."


def action_of(v: dict, result: str) -> str:
    if result == "caught":
        return "No action is necessary, because the check caught its planted bug."
    if result == "recorded" and (store.ladder(v) or 0) >= 4:
        return "Its conformance link does not pass, or its record is not Formal. Finish its conformance run (understando formalize)."
    return {"cannot-fail": "Change this check so that it can fail, or replace it.",
            "broken": "Repair this check: it fails or does not complete.",
            "no-bug": "Plant a bug for this check (understando probe), so a run shows that it can fail.",
            "recorded": "It is a record of a past run. Run it again, or accept the record as it stands.",
            "none": "Add a check for this claim (understando build)."}[result]


def bar_of(surface: str, risky: bool, met: bool, why: str, part: str | None) -> dict:
    level, need = RISKY_BAR if surface == "backend" and risky else BAR.get(surface, BAR["other"])
    return {"surface": surface, "surfaces": [surface], "mixed": False, "risky": risky, "level": level, "need": need, "met": met,
            "why": why or ("" if met else "no check that a planted bug proved"), "part": part,
            "text": f"Bar: {need} · {'met' if met else 'below'}"}


def claim_row(cl: dict, rc: dict, checks: dict[str, dict]) -> dict:
    vs = [checks[i] for i in cl["checks"] if i in checks] or [none_check(cl["id"])]
    rows = [{"id": v["id"], "name": v.get("name") or v["id"], "kind": v["kind"], "strength": strength_of(v), "result": result_of(v)} for v in vs]
    tools = [r for r in rows if r["kind"] != "none"]
    counts = {r: sum(1 for x in tools if x["result"] == r) for r in WORDS if any(x["result"] == r for x in tools)}
    if len(tools) == 1:
        summary = f"1 check: it {ONE[tools[0]['result']]}."
    elif tools:
        summary = f"{len(tools)} checks: " + ", ".join(f"{n} {(ONE if n == 1 and r != 'caught' else WORDS)[r]}" for r, n in counts.items()) + "."
    else:
        summary = "No check backs this claim."
    many = len(rc["parts"]) > 1
    weak = max(rc["parts"], key=lambda p: (strength.ORDER.index(p["verdict"]), -(p["tier"] or 0)))
    pick = next((r for r in rows if r["id"] == weak["best"]), None) or rows[0]
    lead = f"The weakest part is: {next((p['text'] for p in cl.get('parts') or [] if p['id'] == weak['part']), weak['part']).rstrip('.')}. " if many else ""
    text = lead + (f"The {'best' if many else 'strongest'} check is {pick['name']}. {SAID[pick['result']]}" if pick["kind"] != "none" else SAID["none"])
    if pick["result"] == "caught" and rc["verdict"] == "Backed":
        text += " It stays Backed: the user has not accepted an invariant that backs it."
    action = action_of(next((v for v in vs if v["id"] == pick["id"]), vs[0]), pick["result"])
    if pick["result"] == "caught" and rc["verdict"] == "Backed":
        action = "Ask the user to accept the invariant of this claim (understando discover)."
    flagged = [r for r in tools if r["result"] in ("cannot-fail", "broken")]
    warn = None
    if flagged:
        word = {"cannot-fail": "cannot fail", "broken": "fails at the head"}[flagged[0]["result"]]
        warn = {"text": f"{len(flagged)} of {len(tools)} {'check' if len(tools) == 1 else 'checks'} "
                        f"{word if len(flagged) == 1 else 'missed their bug, cannot fail or fail'}: {listing([r['name'] for r in flagged])}. Fix it or drop it.",
                "checks": [r["id"] for r in flagged], "action": action_of(checks[flagged[0]["id"]], flagged[0]["result"])}
    parts = [{"id": p["part"], "text": next((x["text"] for x in cl["parts"] if x["id"] == p["part"]), p["part"]), "strength": p["verdict"],
              "check": (checks.get(p["best"]) or {}).get("name") if p["best"] else None} for p in rc["parts"]] if many else []
    return {"strength": rc["verdict"], "tier": rc["tier"], "checks": rows, "n": len(tools), "counts": counts, "summary": summary,
            "weakest": {"id": pick["id"], "name": pick["name"], "result": pick["result"], "strength": rc["verdict"], "text": text, "action": action,
                        "part": weak["part"] if many else None},
            "flagged": warn, "parts": parts, "bar": bar_of(rc["surface"], rc["risky"], rc["bar_met"], rc["why"], weak["part"] if many else None)}


def verify_block(checks: dict[str, dict], controls: list[dict], claims_of: dict[str, list[str]], names: dict[str, str]) -> dict:
    tools = [v for v in checks.values() if v["kind"] != "none"]
    result = {v["id"]: result_of(v) for v in tools}
    ran = [v for v in tools if result[v["id"]] in ("caught", "cannot-fail")]
    caught = [v for v in ran if result[v["id"]] == "caught"]
    cannot = [v for v in ran if result[v["id"]] == "cannot-fail"]
    line = f"{len(caught)} of {len(ran)} checks caught their planted bug." + (f" {len(cannot)} cannot fail." if cannot else "")
    rest = len(tools) - len(ran)
    other = (f"{rest} more {'check has' if rest == 1 else 'checks have'} no planted bug: records of a past run, mechanical checks or checks that no control ran."
             if rest else "")
    weak = []
    for v in cannot:
        k = next((k for k in controls if k["check"] == v["id"] and strength.outcome(v, k) != "caught"), None)
        if not k:
            continue
        other_v = next((checks[o["check"]] for o in controls if o["check"] != v["id"] and o["check"] in checks and strength.outcome(checks[o["check"]], o) == "caught"
                        and o.get("edits") == k.get("edits")), None)
        own = claims_of.get(v["id"], [])
        weak.append({"check": v["id"], "control": k["id"], "name": v.get("name") or v["id"], "broke": broke(k),
                     "happened": "The check passed on each planted bug, so it can fail on nothing.",
                     "why": f"So this check does not protect {listing([names[c] for c in own])}." if own else "So this check protects no claim.",
                     "action": action_of(v, result[v["id"]]), "ids": " · ".join([k["id"], v["id"], *own]), "claims": own,
                     "caught_by": {"check": other_v["id"], "name": other_v.get("name") or other_v["id"], "control": next(o["id"] for o in controls if o["check"] == other_v["id"]), "missed": k["id"]}
                     if other_v else None})
    return {"result": line, "other": other, "tone": "err" if cannot else "ok", "checks": len(tools), "ran": len(ran),
            "caught": len(caught), "missed": 0, "cannot": len(cannot), "weak": weak, "broke": {k["id"]: broke(k) for k in controls}}


def derived(data: dict, rep: dict, head: str, checks: dict[str, dict], controls: list[dict], refs: dict[str, dict]) -> dict:
    """`checks` and `controls` are the ones of the trust map (each check backs a claim); `refs` maps a check id to its test ref."""
    by_claim = {c["id"]: c for c in rep["claims"]}
    claims = {cl["id"]: claim_row(cl, by_claim[cl["id"]], checks) for cl in data["claims"]}
    claims_of = {i: [cl["id"] for cl in data["claims"] if i in cl["checks"]] for i in checks}
    names = {cl["id"]: cl.get("name") or cl["text"] for cl in data["claims"]}
    rows = {i: {"id": i, "name": v.get("name") or i, "kind": v["kind"], "result": result_of(v),
                "claims": [{"id": c, "name": names[c], "parts": []} for c in claims_of[i]], "tests": [], "controls": [k["id"] for k in controls if k["check"] == i],
                "ref": refs.get(i)} for i, v in checks.items()}
    return {"schema": 2, "head": head, "claims": claims, "checks": rows, "verify": verify_block(checks, controls, claims_of, names)}
