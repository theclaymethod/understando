#!/usr/bin/env python3
"""The values that understando derives once from a trust map, for every reader of it.

The review CLI (the blocker count of a stop), the PR-body section and the explainer page all read
these values, so they can never disagree. `understando explain` writes them into the `derived`
block of refs.resolved.json, and the visual-explainer trust-map components render them; they do
not compute them again.

  promises     each promise with its strength (the verdict of its weakest claim), its claims,
               weakest first (ties keep the map order), and its claim count and tally
  claims       each claim with its strength (the strength of its weakest check), its checks and
               their results ("5 checks: 4 caught their bug, 1 missed"), and the weakest check,
               named in plain words, with its action
  verify       "Can these checks catch a bug?": the count of checks that caught their planted bug,
               one card for each check that missed its bug or cannot fail, the checks that caught
               their bug by promise, and the checks for each tier
  merge        the merge verdict: "not-ready" (with the blockers), "accept" (with the risks to
               accept) or "ready", and the risks to accept in each form (`accept`), for the checklist
               of the guided review
  unclaimed    the changed source files outside the claims, with their risk and one action, the
               core files that claims cover in part, and the summary lines (risky files first)
  bugs         the possible bugs of the invariants, in the find-bugs heading format (findings.py)
  spine        each changed file in its chapter of the change (explain.json change.chapters), with
               its protection, its claims and its "look closely" flags (from verified sources only),
               the imports between the chapters, and the files in GitHub's order
  checks       each check with its result, the claims and parts that it backs and the test it runs;
  tests        the changed test files as the checks they provide, and the changed tests that back
               no claim

A file is covered when a claim's code refs cite it, when a claim names it, when one of the
claim's checks exercises it (the coverage record of the run: `understando coverage`), or when a
control of one of its checks edits it.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import findings  # noqa: E402
import names  # noqa: E402
import onto  # noqa: E402
import tm  # noqa: E402

SCHEMA = 2
VERDICTS = ["Formal", "Proven", "Backed", "Asserted", "Gap"]
STRONG = ("Formal", "Proven")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def weakest(verdicts) -> str | None:
    found = [v for v in verdicts if v]
    return max(found, key=VERDICTS.index) if found else None


def promises_in_order(data: dict) -> list[tuple[dict, str, list[str]]]:
    """Each promise with its strength and its claims, weakest first; ties keep the map order."""
    verdict_of = {c["id"]: c["verdict"] for c in data["claims"]}
    rows = []
    for p in data["promises"]:
        cids = sorted(p["claims"], key=lambda c: (-VERDICTS.index(verdict_of[c]), c))
        rows.append((p, weakest(verdict_of[c] for c in cids), cids))
    return sorted(rows, key=lambda r: -VERDICTS.index(r[1]))


def tally(verdicts: list[str]) -> str:
    return ", ".join(f"{verdicts.count(v)} {v}" for v in VERDICTS if v in verdicts)


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]


def merge_verdict(data: dict, ready: dict | None = None, risky_unclaimed: int = 0, cfg: dict | None = None) -> tuple[str, list[dict]]:
    """Can the reviewer merge? A promise at Gap or Asserted with a reviewer action blocks, unless
    each of its weak claims is waived; a failed ready gate blocks; a risky claim below its evidence
    bar blocks (onto.bar). A Backed promise with a reviewer action, a waived claim, a claim below its
    bar that is not risky, and changed code with risk and no claim are risks to accept.
    Returns ("not-ready" | "accept" | "ready", items); each item has label, text and href."""
    blocking, accept = merge_items(data, ready, risky_unclaimed, cfg)
    if blocking:
        return "not-ready", blocking
    return ("accept", accept) if accept else ("ready", [])


def merge_items(data: dict, ready: dict | None = None, risky_unclaimed: int = 0, cfg: dict | None = None) -> tuple[list[dict], list[dict]]:
    """The blockers and the risks to accept of merge_verdict, each in the order of the review:
    the failed gates, the promises weakest first, then the claims below their bar. The guided
    review lists both, so a reviewer sees the risks to accept also while the PR is not ready."""
    claims = {c["id"]: c for c in data["claims"]}
    blocking, accept = [], []
    for g in (ready or {}).get("gates", []):
        if not g["pass"]:
            blocking.append({"label": f"Gate {g['n']}, {g['name']}", "text": g["detail"], "href": "#story-ready"})
    for p, strength, cids in promises_in_order(data):
        action = p.get("reviewer_action")
        weak = [claims[c] for c in cids if claims[c]["verdict"] in ("Gap", "Asserted")]
        href = f"#promise-{slug(p['id'])}"
        if strength in ("Gap", "Asserted") and action and not all(c.get("waiver") for c in weak):
            blocking.append({"label": p["label"], "text": first_sentence(action), "href": href})
        elif action and strength not in STRONG:
            accept.append({"label": p["label"], "text": first_sentence(action), "href": href})
        for c in weak:
            if c.get("waiver"):
                accept.append({"label": p["label"], "text": "Waived: " + c["waiver"]["reason"], "href": f"#claim-{slug(c['id'])}"})
    for c in data["claims"]:
        b = onto.bar(data, c, cfg)
        if b["met"] or c.get("waiver"):
            continue
        item = {"label": names.of(data, c["id"]), "text": bar_sentence(b), "href": f"#claim-{slug(c['id'])}"}
        (blocking if b["risky"] else accept).append(item)
    if risky_unclaimed:
        n = risky_unclaimed
        accept.append({"label": "Unclaimed changes", "text": f"{n} changed {'file has' if n == 1 else 'files have'} risk and no claim. Read {'it' if n == 1 else 'them'} before you approve.",
                       "href": "#unclaimed"})
    return blocking, accept


# ---- Evidence bars (references/evidence-bars.md) ------------------------------------------

def bar_sentence(b: dict) -> str:
    """A below-bar claim, in the words of its bar."""
    why = b["why"]
    if b["level"] in ("degraded-eval", "eval") and "degraded" in why:
        return "Its eval has no degraded variant, so it cannot show that it can fail."
    if why.startswith("only a model judgment"):
        return "Only a model judgment backs it. Its bar is an eval with a degraded control."
    if why.startswith("only tests"):
        return "Only tests back it. Its bar is an eval with a degraded control."
    if b["level"] in ("video", "e2e"):
        return f"It has {why}. Its bar is a browser e2e with a recorded video." if why.startswith("an e2e") else f"{capital(why)}. Its bar is a browser e2e with a recorded video."
    need = {"formal": "a proof", "property": "a property test or a static rule", "static": "types or a static rule", "test": "a test that caught a planted bug",
            "check": "a check"}.get(b["level"], b["need"])
    return f"{capital(why)}. Its bar is {need}."


SURFACE_BAR = {"backend": "a proof, or a property test, type or static rule that caught a planted bug",
               "llm": "a recorded eval with a degraded variant", "frontend": "a browser e2e with a recorded video", "other": "a check that backs it"}


def bars_summary(data: dict, rows: dict[str, dict]) -> dict:
    """The bar counts and the story line: which bars the PR met, and what is below its bar."""
    claims = data["claims"]
    met = [c for c in claims if rows[c["id"]]["bar"]["met"]]
    risky_below = [c for c in claims if not rows[c["id"]]["bar"]["met"] and rows[c["id"]]["bar"]["risky"] and not c.get("waiver")]
    summary = (f"{len(met)} of {len(claims)} claims meet their bar. "
               + (f"{len(risky_below)} risky {'claim is' if len(risky_below) == 1 else 'claims are'} below it." if risky_below else "No risky claim is below it."))
    story = []
    for surf in ("backend", "llm", "frontend", "other"):
        own = [c for c in claims if rows[c["id"]]["bar"]["surface"] == surf]
        if not own:
            continue
        m = sum(1 for c in own if rows[c["id"]]["bar"]["met"])
        story.append(f"{m} of {len(own)} {surf if surf != 'llm' else 'LLM'} claims meet their bar: {SURFACE_BAR[surf]}.")
    below = [c for c in claims if not rows[c["id"]]["bar"]["met"]]
    if below:
        story.append("Below the bar: " + names.listing([names.of(data, c["id"]) for c in below], top=4) + ".")
    return {"met": len(met), "total": len(claims), "risky_below": [c["id"] for c in risky_below],
            "risky_below_names": [names.of(data, c["id"]) for c in risky_below], "summary": summary, "story": story}


# ---- Claims and their checks ---------------------------------------------------------------------

RESULT_WORDS = {"caught": "caught their bug", "missed": "missed", "cannot-fail": "cannot fail", "no-bug": "had no planted bug",
                "recorded": "are records of a past run", "checked": "are mechanical checks", "broken": "fail at the head",
                "none": "are only the PR text"}
RESULT_ONE = {"caught": "caught its bug", "missed": "missed", "cannot-fail": "cannot fail", "no-bug": "had no planted bug",
              "recorded": "is a record of a past run", "checked": "is a mechanical check", "broken": "fails at the head",
              "none": "is only the PR text"}


def check_name(data: dict, v: dict) -> str:
    return v.get("name") or names.verifier_name(v, {c["id"]: c for c in data["claims"]})


def fixes(data: dict, explain: dict | None) -> dict[str, str]:
    """The cheapest fix of explain.json risks, for each claim id and each legacy id."""
    out: dict[str, str] = {}
    for r in (explain or {}).get("risks") or []:
        for cid in r.get("claims", []):
            if r.get("fix"):
                out.setdefault(cid, r["fix"])
    for c in data["claims"]:
        for old in c.get("legacy_ids") or []:
            if old in out:
                out.setdefault(c["id"], out[old])
    return out


def same_bug_catcher(data: dict, v: dict) -> dict | None:
    """A check that caught a planted bug with the same edits as a bug that `v` missed."""
    hit = same_bug(data, v)
    return hit[0] if hit else None


def same_bug(data: dict, v: dict) -> tuple[dict, dict, dict] | None:
    """(the other check, its control, the control of `v`): one planted bug, two results."""
    import verdicts
    mine = [k for k in data["controls"] if k["verifier"] == v["id"] and verdicts.control_outcome(k) != "caught"]
    for k in mine:
        for o in data["controls"]:
            if o["verifier"] != v["id"] and verdicts.control_outcome(o) == "caught" and o.get("edits") == k.get("edits"):
                return next(x for x in data["verifiers"] if x["id"] == o["verifier"]), o, k
    return None


def check_action(data: dict, v: dict, claim: dict, result: str, fix: str | None) -> str:
    """One reviewer action for a check, in plain words."""
    if v.get("formal_record") and (v["formal_record"].get("formal") or {}).get("verdict") != "Formal":
        return "Its formal record is not Formal yet. Finish its conformance run (understando formalize)."
    if result == "caught":
        return "No action: it caught its planted bug."
    if result == "none":
        base = ("Only the PR text states it. Add a check (understando close), or accept the risk." if claim.get("stated")
                else "No check exists, and the PR text does not state it. Decide if it matters. To close it, add a check (understando close).")
        return base + (f" The cheapest way: {fix}" if fix else "")
    if result == "missed":
        other = same_bug_catcher(data, v)
        if other:
            return f"Trust {check_name(data, other)}, not this check."
    if result == "recorded" and (tm.ladder(v) or 0) >= 4:
        return "No planted bug broke this proof or model. Plant one for this property (understando formalize), so a run shows that it can fail."
    if result == "recorded" and v.get("tier") == "guess":
        return "Treat it as one opinion. Ask a model of another family to check it, or read the evidence yourself."
    if result == "recorded" and (v.get("formal_record") or {}).get("formal", {}).get("verdict") not in (None, "Formal"):
        return "Its formal record is not Formal yet. Finish its conformance run (understando formalize)."
    if v.get("formal_record") and (v["formal_record"].get("formal") or {}).get("verdict") != "Formal":
        return "Its formal record is not Formal yet. Finish its conformance run (understando formalize)."
    base = {"missed": "Add a check that fails on this bug, or change this check so that it does.",
            "cannot-fail": "Change this check so that it can fail, or replace it (understando close).",
            "broken": "Repair this check: it fails or does not complete at the PR head.",
            "no-bug": "Plant a bug for this check (understando probe), or accept the claim as it stands.",
            "recorded": "It is a record of a past run. Run it again, or accept the record as it stands.",
            "checked": "Plant a bug for this mechanical check, or add a CI rule that keeps it true."}[result]
    return base + (f" The cheapest way: {fix}" if fix and result != "recorded" else "")


def claim_rows(data: dict, explain: dict | None = None, cfg: dict | None = None) -> dict[str, dict]:
    """Each claim: its strength (its weakest part; a part is as strong as its strongest check), its
    checks with their result, the summary line ("5 checks: 4 caught their bug, 1 missed."), the
    evidence of the weakest part with its action, the flagged checks (a warning with an action, not
    a score), its parts, and its evidence bar (onto.bar)."""
    import verdicts
    fx = fixes(data, explain)
    out = {}
    for c in data["claims"]:
        checks = onto.checks_of(data, c)
        rows = [{"id": v["id"], "name": check_name(data, v), "kind": v["kind"], "strength": onto.check_strength(data, v, c),
                 "result": onto.check_result(data, v)} for v in checks]
        tools = [r for r in rows if r["kind"] != "none"]
        counts = {r: sum(1 for x in tools if x["result"] == r) for r in onto.RESULTS if any(x["result"] == r for x in tools)}
        order = ["caught", "missed", "cannot-fail", "broken", "no-bug", "recorded", "checked"]
        bits = [f"{counts[r]} {(RESULT_ONE if counts[r] == 1 and r not in ('caught',) else RESULT_WORDS)[r]}" for r in order if r in counts]
        if len(tools) == 1:
            summary = f"1 check: it {RESULT_ONE[tools[0]['result']]}."
        elif tools:
            summary = f"{len(tools)} checks: {', '.join(bits)}."
        else:
            summary = "No check: only the PR text states it." if c.get("stated") else "No check, and the PR text does not state it."
        parts = onto.parts_of(data, c)
        strength, part, weak = onto.claim_strength(data, c)
        many = len(parts) > 1
        lead = f"The weakest part is: {part['text'].rstrip('.')}. " if many and part else ""
        w = None
        if weak:
            result = onto.check_result(data, weak)
            name = check_name(data, weak)
            whose = "its best check" if many else "the strongest check"
            said = {"caught": f"{lead}{capital(whose)} is {name}. It caught its planted bug.",
                    "missed": f"{lead}{capital(whose)} is {name}. It missed its planted bug.",
                    "cannot-fail": f"{lead}{capital(whose)} is {name}. It cannot fail: it passed on each planted bug.",
                    "broken": f"{lead}{capital(whose)} is {name}. It fails or does not complete at the PR head.",
                    "no-bug": f"{lead}{capital(whose)} is {name}. No planted bug ran, so no run proved that it can fail.",
                    "recorded": f"{lead}{capital(whose)} is {name}. It is a record of a past run, and we did not run it again.",
                    "checked": f"{lead}{capital(whose)} is {name}. It is a mechanical check with no planted bug.",
                    "none": lead + ("No tool checks it. Only the PR text states it." if part["stated"] else
                                    "No tool checks it, and the PR text does not state it.")}[result]
            pc = {"stated": part["stated"], "invariants": part["invariants"]}
            if strength == "Backed" and not onto.intent(data, pc) and onto.check_strength(data, weak, {"stated": True}) != "Backed":
                said += " It stays Backed: the PR does not state it, and no invariant that the user confirmed backs it."
            if result == "caught" and strength == "Backed" and (tm.ladder(weak) or 0) >= 4 and not weak.get("formal_record"):
                said += " Its conformance link does not pass, so it counts only as Backed."
            action = check_action(data, weak, c, result, fx.get(c["id"]))
            bug = next((b for b in (verdicts.disagreeing(data, i) for i in part["invariants"]) if b), None)
            if bug:
                said = f"The code disagrees with a rule that the user confirmed: {names.of(data, bug['id'])}. " + said
                action = "Do not trust this claim until the code change lands: see the bugs found." + (
                    " Then " + action[0].lower() + action[1:] if not action.startswith("No action") else "")
            w = {"id": weak["id"], "name": name, "result": result, "strength": strength, "text": said, "action": action,
                 "part": part["id"] if many else None}
        flags = onto.flagged(data, c)
        warn = None
        if flags:
            f = flags[0]
            r = onto.check_result(data, f)
            word = {"missed": "missed its bug", "cannot-fail": "cannot fail", "broken": "fails at the head"}[r]
            warn = {"text": f"{len(flags)} of {len(tools)} {'check' if len(tools) == 1 else 'checks'} {word if len(flags) == 1 else 'missed their bug, cannot fail or fail'}: "
                            f"{names.listing([check_name(data, x) for x in flags])}. Fix it or drop it.",
                    "checks": [x["id"] for x in flags], "action": check_action(data, f, c, r, fx.get(c["id"]))}
        part_rows = [{"id": p["id"], "text": p["text"], "strength": st, "check": check_name(data, best) if best else None}
                     for p in parts for st, best in [onto.part_strength(data, p)]] if many else []
        out[c["id"]] = {"strength": c.get("verdict") or strength, "tier": c.get("tier"), "checks": rows, "n": len(tools),
                        "counts": counts, "summary": summary, "weakest": w, "flagged": warn, "parts": part_rows,
                        "bar": onto.bar(data, c, cfg)}
    return out


def capital(text: str) -> str:
    return text[:1].upper() + text[1:]


# ---- Can these checks catch a bug? ---------------------------------------------------------------

RECIPE_SENTENCE = {
    "remove-guard-line": "We deleted a guard line{where}.",
    "invert-condition": "We inverted a condition{where}.",
    "remove-type-pin": "We removed a type pin{where}, so the type error shows.",
    "drop-allowlist-row": "We deleted one row of an allowlist{where}.",
    "corrupt-golden-byte": "We changed one byte of the golden file{where}.",
    "remove-covered-code": "We changed the code that the check covers{where}.",
    "plant-violation": "We planted a break of the rule{where}.",
}
MAX_BROKE_WORDS = 20


def broke(k: dict) -> str:
    """What we broke, as one full short sentence: the control's name, else the first sentence of its
    description when it has at most 20 words, else a sentence from its recipe. Never a cut sentence."""
    if k.get("name"):
        return k["name"]
    first = first_sentence(k.get("description") or "")
    if first and len(first.split()) <= MAX_BROKE_WORDS:
        return first if first.endswith((".", "!", "?")) else first + "."
    e = (k.get("edits") or [{}])[0]
    where = f" in {e['symbol']}" if isinstance(e.get("symbol"), str) else (f" in {e['path'].rsplit('/', 1)[-1]}" if e.get("path") else "")
    return RECIPE_SENTENCE.get(k.get("recipe"), "We planted a bug{where}.").format(where=where)


RUNG_WORDS = {5: "Formal proof", 4: "Model check", 3: "Types and import rules", 2: "Property tests", 1: "Tests"}


def verify(data: dict, refs_promises: list[dict], explain: dict | None = None) -> dict:
    """Can these checks catch a bug? It counts checks, not planted bugs. A check caught its bug when
    each of its planted bugs made it fail."""
    import verdicts
    rows = claim_rows(data, explain)
    fx = fixes(data, explain)
    tools = [v for v in data["verifiers"] if onto.is_tool(v)]
    result = {v["id"]: onto.check_result(data, v) for v in tools}
    ran = [v for v in tools if result[v["id"]] in ("caught", "missed", "cannot-fail")]
    caught = [v for v in ran if result[v["id"]] == "caught"]
    missed = [v for v in ran if result[v["id"]] == "missed"]
    cannot = [v for v in ran if result[v["id"]] == "cannot-fail"]
    tail = [f"{len(missed)} missed {'it' if len(missed) == 1 else 'theirs'}" if missed else "", f"{len(cannot)} cannot fail" if cannot else ""]
    line = f"{len(caught)} of {len(ran)} checks caught their planted bug." + (" " + " and ".join(t for t in tail if t).capitalize() + "." if any(tail) else "")
    rest = len(tools) - len(ran)
    other = (f"{rest} more {'check has' if rest == 1 else 'checks have'} no planted bug: records of a past run, mechanical checks or checks that no control ran."
             if rest else "")
    tone = "err" if cannot else "warn" if missed else "ok"
    weak = []
    for v in missed + cannot:
        own = [c for c in onto.claims_of(data, v)]
        k = next((k for k in data["controls"] if k["verifier"] == v["id"] and verdicts.control_outcome(k) != "caught"), None)
        if not k:
            continue
        protects = [names.of(data, c["id"]) for c in own]
        other_v = same_bug_catcher(data, v)
        why = f"So this check does not protect {names.listing(protects)}." + (f" Only {check_name(data, other_v)} caught the same bug." if other_v else "")
        action = check_action(data, v, own[0] if own else {}, result[v["id"]], next((fx.get(c["id"]) for c in own if fx.get(c["id"])), None))
        happened = "The check passed on each planted bug, so it can fail on nothing." if result[v["id"]] == "cannot-fail" else "The check still passed."
        pair = same_bug(data, v)
        caught_by = {"check": pair[0]["id"], "name": check_name(data, pair[0]), "control": pair[1]["id"], "missed": pair[2]["id"]} if pair else None
        weak.append({"check": v["id"], "control": k["id"], "name": check_name(data, v), "broke": broke(k), "happened": happened, "why": why,
                     "action": action, "ids": " · ".join([k["id"], v["id"], *[c["id"] for c in own]]), "claims": [c["id"] for c in own],
                     "caught_by": caught_by})
    by_promise = []
    for p in refs_promises:
        got = [{"check": vid, "name": check_name(data, v), "claim": names.of(data, cid),
                "broke": [broke(k) for k in data["controls"] if k["verifier"] == vid and verdicts.control_outcome(k) == "caught"],
                "ids": " · ".join([vid, *[k["id"] for k in data["controls"] if k["verifier"] == vid]])}
               for cid in p["claims"] for v in onto.checks_of(data, cid) for vid in [v["id"]] if result.get(vid) == "caught"]
        if got:
            by_promise.append({"id": p["id"], "rows": got})
    counts: dict[str, int] = {}
    for v in tools:
        rung = tm.ladder(v)
        word = RUNG_WORDS[rung] if rung else "Recorded runs and model judgments"
        counts[word] = counts.get(word, 0) + 1
    tiers = [{"label": w, "n": counts[w]} for w in [*[RUNG_WORDS[n] for n in (5, 4, 3, 2, 1)], "Recorded runs and model judgments"] if w in counts]
    evals = []
    for v in tools:
        if v["kind"] != "eval":
            continue
        d = (v.get("eval") or {}).get("degraded")
        real = (v.get("recorded") or {}).get("result", "")
        text = (f"The real run scored {d['baseline']}. The degraded run ({d['variant']}) scored {d['score']}."
                + ("" if onto.eval_degraded(v) else " It did not score worse, so the eval cannot show that it can fail.")) if d else \
            "Flagged: no degraded run, so the eval cannot show that it can fail."
        evals.append({"check": v["id"], "name": check_name(data, v), "claim": names.of(data, (onto.claims_of(data, v) or [{"id": ""}])[0]["id"]),
                      "real": real, "degraded": d, "flagged": not onto.eval_degraded(v), "text": text,
                      "action": "" if onto.eval_degraded(v) else "Run one planted-degraded variant (an ablated prompt, a removed rule, a weaker model or a shuffled input), and record its score."})
    ui = []
    for v in tools:
        art = v.get("artifact") or {}
        own = onto.claims_of(data, v)
        if not art.get("video") and not any(onto.surface(data, c) == "frontend" for c in own):
            continue
        shots = art.get("screenshots") or []
        ui.append({"check": v["id"], "name": check_name(data, v), "claim": names.of(data, own[0]["id"]) if own else "",
                   "video": art.get("video"), "poster": shots[0] if shots else None, "screenshots": shots, "captions": art.get("captions"),
                   "summary": art.get("summary") or "", "caught": result[v["id"]] == "caught",
                   "text": ("The UI run caught the planted break." if result[v["id"]] == "caught" else "No planted break of the UI made this run fail.")
                           + ("" if art.get("video") else " It has no recorded video.")})
    return {"result": line, "other": other, "tone": tone, "checks": len(tools), "ran": len(ran), "caught": len(caught), "evals": evals, "ui": ui,
            "missed": len(missed), "cannot": len(cannot), "weak": weak, "by_promise": by_promise, "tiers": tiers,
            "broke": {k["id"]: broke(k) for k in data["controls"]}}


# ---- Unclaimed changes ---------------------------------------------------------------------

CODE_EXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".jsx", ".sh", ".go", ".rs", ".java", ".kt",
            ".rb", ".swift", ".c", ".h", ".cc", ".cpp", ".cs", ".php", ".scala"}
# A changed file carries risk when it is new and large, or when its path or its changed symbols
# touch money, safety or I/O. A change of fewer than SMALL lines is low risk, whatever it touches.
TOUCHES = [
    (re.compile(r"cost|price|billing|meter|payment|budget|usd|invoice", re.I), "touches money"),
    (re.compile(r"safety|auth|secret|permission|sandbox|redact|harm|privacy", re.I), "touches safety"),
    (re.compile(r"transport|http|socket|subprocess|network|upload|download|(^|/)cli\.py$|exit_code", re.I), "touches I/O"),
]
SMALL = 20
LARGE = 100


def is_test(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    return (any(p in ("tests", "test", "__tests__", "spec") for p in parts[:-1]) or name.startswith("test_")
            or re.search(r"(_test|\.test|\.spec)\.\w+$", name) is not None)


def is_code(path: str) -> bool:
    return Path(path).suffix in CODE_EXT and not is_test(path)


def diff_root(files) -> str:
    code = [p.split("/") for p in files if is_code(p)]
    if len(code) < 2:
        return ""
    parts = code[0]
    for q in code[1:]:
        i = 0
        while i < len(parts) and i < len(q) and parts[i] == q[i]:
            i += 1
        parts = parts[:i]
    return "/".join(parts) + "/" if parts else ""


def lines(n: int, sign: str) -> str:
    return f"{sign}{n:,}" if n else "0"


def humanize(path: str) -> str:
    """A role phrase for a file that explain.json gives no role: "the <name> code". Write a real role
    in explain.json unclaimed.roles: "the UAP adapter", "the CLI and its exit codes"."""
    name = path.split("/")[-1].rsplit(".", 1)[0].lstrip("_")
    if name == "init":
        name = path.split("/")[-2] if "/" in path else name
    return "the " + re.sub(r"[_-]+", " ", name) + " code"


def named_files(data: dict, files) -> dict[str, set[str]]:
    """The changed files that a claim names in its text, its plain text or its parts: the path, or a
    file name that only one changed file has."""
    base: dict[str, list[str]] = {}
    for p in files:
        base.setdefault(p.rsplit("/", 1)[-1], []).append(p)
    out: dict[str, set[str]] = {}
    for c in data["claims"]:
        text = " ".join([c.get("text", ""), (c.get("plain") or {}).get("what", ""), *[x.get("text", "") for x in c.get("parts") or []]])
        for p in files:
            name = p.rsplit("/", 1)[-1]
            if p in text or (len(base[name]) == 1 and "." in name and re.search(r"(?<![\w/.-])" + re.escape(name) + r"(?![\w-])", text)):
                out.setdefault(p, set()).add(c["id"])
    return out


def exercised_files(data: dict, coverage: dict | None, files) -> dict[str, set[str]]:
    """The changed files that a check of a claim runs, from the coverage record of the run
    ({check id: [paths]}, `understando coverage`), as {path: claim ids}."""
    out: dict[str, set[str]] = {}
    for c in data["claims"]:
        for v in onto.checks_of(data, c):
            for p in (coverage or {}).get(v["id"]) or []:
                if p in files:
                    out.setdefault(p, set()).add(c["id"])
    return out


def edited_files(data: dict, files) -> dict[str, set[str]]:
    """The changed files that a control of a check of a claim edits: the mechanical fallback. A
    plant-violation control does not count: it adds a break of a rule, so it tests the rule."""
    controls: dict[str, list[dict]] = {}
    for k in data["controls"]:
        controls.setdefault(k["verifier"], []).append(k)
    out: dict[str, set[str]] = {}
    for c in data["claims"]:
        for v in onto.checks_of(data, c):
            for k in controls.get(v["id"], []):
                if k.get("recipe") == "plant-violation":
                    continue  # a planted break of a rule tests the rule, not the code of the file it lands in
                for e in k.get("edits") or []:
                    hits = [p for p in files if p == e.get("path") or p.endswith("/" + str(e.get("path", "")))]
                    for p in hits if len(hits) == 1 else []:
                        out.setdefault(p, set()).add(c["id"])
    return out


def unclaimed(data: dict, refs: dict, spec: dict | None = None, coverage: dict | None = None) -> dict:
    """The changed source files outside the claims, from the diff, the claim code refs, the claim
    texts, the coverage record of the checks and the control edits. A core file (explain.json
    unclaimed.core) that claims cite or exercise is covered in part, with the share of its new
    lines that claims cite. Each other file that no claim covers gets its risks and one action,
    chosen by rule: touches money, safety or I/O: add a check; new and 100 lines or more: ask for a
    claim; 100 changed lines or more: read it; else skim. A core file that no claim covers comes
    first. A file is covered when a claim cites it (under a tenth of a large file does not count),
    names it, or has a check that runs it or a control that edits it."""
    spec = spec or {}
    notes, roles, core = spec.get("notes") or {}, spec.get("roles") or {}, spec.get("core") or []
    diff = refs["diff"]
    files, deleted, created, added, symbols = diff["files"], set(diff["deleted"]), set(diff["created"]), diff["added"], diff.get("symbols") or {}
    bad = [p for p in [*notes, *roles] if p not in files]
    if bad:
        tm.fail("derive: explain.json unclaimed names " + ", ".join(bad) + ", which the diff does not change", 1)
    by_key = {_key(r["ref"]): r for r in refs["refs"]}
    cited: dict[str, tuple[set[int], set[str]]] = {}
    for c in data["claims"]:
        for ref in c.get("code", []):
            r = by_key[_key(ref)]
            span, ids = cited.setdefault(ref["path"], (set(), set()))
            span.update(range(r["span"][0], r["span"][1] + 1))
            ids.add(c["id"])
    named, ran, edited = named_files(data, files), exercised_files(data, coverage, files), edited_files(data, files)
    is_core = lambda p: any(p == x or p.startswith(x.rstrip("/") + "/") for x in core)  # noqa: E731
    root = diff_root(files)
    rows, core_rows = [], []
    for path, (plus, minus) in files.items():
        if not is_code(path) or path in deleted or not plus:
            continue
        ranges = added.get(path) or []
        total = sum(b - a + 1 for a, b in ranges)
        entry = cited.get(path)
        share = sum(1 for a, b in ranges for n in range(a, b + 1) if n in entry[0]) if entry else 0
        new = path in created
        names_ = (symbols.get(path) or {}).get("names") or []
        change = (f"New file of {lines(plus, '')} lines" if new else f"{lines(plus, '+')} / {lines(minus, '−')} lines") + (
            ": " + ", ".join(names_[:3]) + (f" and {len(names_) - 3} more" if len(names_) > 3 else "") if names_ else "")
        by = {"cited": sorted(entry[1]) if entry else [], "named": sorted(named.get(path, ())), "exercised": sorted(ran.get(path, ())),
              "edited": sorted(edited.get(path, ()))}
        claims = set().union(*[set(x) for x in by.values()])
        base = {"path": path, "file": path[len(root):] if root and path.startswith(root) else path, "role": roles.get(path) or humanize(path),
                "change": change, "added": plus, "removed": minus, "created": new, "note": notes.get(path),
                "main": (symbols.get(path) or {}).get("main"), "claims": len(claims), "cited": share, "total": total, "by": by}
        other = by["named"] or by["exercised"] or by["edited"]
        only_run = by["exercised"] and not (by["cited"] or by["named"] or by["edited"])
        if (is_core(path) and claims) or (only_run and plus >= SMALL):
            # A file that a check only runs is covered in part: no claim says what it must do.
            touch = [word for pattern, word in TOUCHES if pattern.search(path) or any(pattern.search(n) for n in names_)] if plus >= SMALL else []
            text = ("Read the lines that no claim cites." if share else
                    "A check runs it, but no claim says what it must do. Read it, or ask the author for a claim." if only_run else
                    "A claim names it or a control edits it, but no claim cites its lines. Read the lines that no claim cites.")
            core_rows.append({**base, "risks": touch, "action": {"kind": "read", "text": text}})
            continue
        if other or (entry and (plus < LARGE or share >= 0.1 * max(total, 1))):
            continue
        if is_core(path):
            rows.append(({**base, "risks": ["core harness file that no claim covers"], "action": {"kind": "ask", "text": "Ask the author for a claim."}}, total + 10**6))
            continue
        touch = [] if plus < SMALL else [word for pattern, word in TOUCHES if pattern.search(path) or any(pattern.search(n) for n in names_)]
        risks = (["new file of 100 lines or more"] if new and plus >= LARGE else []) + touch
        action = ({"kind": "check", "text": "Add a check: an e2e test that runs this code."} if touch
                  else {"kind": "ask", "text": "Ask the author for a claim."} if new and plus >= LARGE
                  else {"kind": "read", "text": "Read it."} if plus >= LARGE else {"kind": "skim", "text": "Low risk: skim."})
        rows.append(({**base, "risks": risks, "action": action}, total - share))
    rows.sort(key=lambda r: (not r[0]["risks"], -r[1], r[0]["path"]))
    core_rows.sort(key=lambda f: (not f["risks"], f["cited"] / max(f["total"], 1), f["path"]))
    out = [r for r, _ in rows]
    return {"files": out, "core": core_rows, "summary": unclaimed_summary(out, core_rows)}


def unclaimed_summary(files: list[dict], partial: list[dict] | None = None) -> dict:
    """The risky files first: "12 risky files have no claim. Read these first." A risky file that a
    check only runs, with no claim about it, joins the lead. Then a quieter line with the count of
    the other files."""
    risky = sum(1 for f in files if f["risks"])
    half = sum(1 for f in partial or [] if f["risks"] and not f["by"]["cited"])
    rest = len(files) - risky
    if not files and not half:
        return {"risky": 0, "partial_risky": 0, "rest": 0, "lead": "Each changed source file has a claim.", "quiet": ""}
    if risky and half:
        lead = (f"{risky} risky {'file has' if risky == 1 else 'files have'} no claim, and a check only runs {half} more risky "
                f"{'file' if half == 1 else 'files'}. Read these first.")
    elif risky or half:
        n = risky or half
        lead = (f"{n} risky {'file has' if n == 1 else 'files have'} no claim. Read {'it' if n == 1 else 'these'} first." if risky else
                f"A check only runs {n} risky {'file' if n == 1 else 'files'}, and no claim says what {'it' if n == 1 else 'they'} must do. Read {'it' if n == 1 else 'these'} first.")
    else:
        lead = "No risky file is without a claim."
    quiet = (f"{rest} other changed {'file has' if rest == 1 else 'files have'} no claim. {'It is' if rest == 1 else 'They are'} low risk: skim {'it' if rest == 1 else 'them'}."
             if rest else "")
    return {"risky": risky, "partial_risky": half, "rest": rest, "lead": lead, "quiet": quiet}


def _key(ref: dict) -> tuple:
    return tuple(sorted((k, repr(v)) for k, v in ref.items() if k != "note"))


# ---- The checks of the PR (verifiers, not tests) ---------------------------------------------

def test_targets(v: dict, files) -> list[tuple[str, str | None]]:
    """The test files (and the test in each, when the command names one) that a check runs, from its
    command: a path with `::name` (pytest), or a dotted module (`python -m unittest tests.test_core.T`)."""
    cmd = v.get("command") or {}
    cwd = (cmd.get("cwd") or "").strip("/")
    join = lambda p: f"{cwd}/{p}" if cwd else p  # noqa: E731
    out: list[tuple[str, str | None]] = []
    for tok in cmd.get("argv") or []:
        path, _, sym = tok.partition("::")
        if path.endswith(".py") and is_test(path):
            out.append((join(path), sym.split("[")[0].replace("::", ".") or None))
            continue
        if re.fullmatch(r"[A-Za-z_][\w]*(\.[A-Za-z_]\w*)+", tok):
            parts = tok.split(".")
            # The module is the longest prefix that is a changed file, else the last part named test_*.
            ks = [k for k in range(len(parts), 0, -1) if join("/".join(parts[:k]) + ".py") in files] or \
                 [k for k in range(len(parts), 0, -1) if parts[k - 1].startswith("test")]
            if ks and is_test(join("/".join(parts[:ks[0]]) + ".py")):
                out.append((join("/".join(parts[:ks[0]]) + ".py"), ".".join(parts[ks[0]:]) or None))
    return out


def checks_view(data: dict, refs: dict, rows: dict[str, dict]) -> tuple[dict, dict]:
    """Each check of the map, as the guided review shows it: its name, its kind, its result (caught,
    missed, cannot fail ...), the claims and the parts that it backs, and the test that it runs. Then
    the changed test files, each as the checks that it provides, and the changed tests that back no
    claim (no check runs them), by file, with one action."""
    diff = refs["diff"]
    files, symbols, deleted = diff["files"], diff.get("symbols") or {}, set(diff["deleted"])
    root = diff_root(files)
    short = lambda p: p[len(root):] if root and p.startswith(root) else p  # noqa: E731
    controls: dict[str, list[str]] = {}
    for k in data["controls"]:
        controls.setdefault(k["verifier"], []).append(k["id"])
    out: dict[str, dict] = {}
    runs: dict[str, list[tuple[str, str | None]]] = {}
    for v in data["verifiers"]:
        if not onto.is_tool(v):
            continue
        backs = []
        for c in onto.claims_of(data, v):
            parts = [p["text"] for p in onto.parts_of(data, c) if any(x["id"] == v["id"] for x in p["checks"])] if c.get("parts") else []
            backs.append({"id": c["id"], "name": names.of(data, c["id"]), "parts": parts})
        targets = test_targets(v, files)
        for path, sym in targets:
            runs.setdefault(path, []).append((v["id"], sym))
        main = next(((p, s) for p, s in targets if s), None)
        out[v["id"]] = {"id": v["id"], "name": check_name(data, v), "kind": v["kind"], "result": onto.check_result(data, v), "claims": backs,
                        "tests": [{"path": p, "file": short(p), "symbol": s} for p, s in targets], "controls": controls.get(v["id"], []),
                        "ref": {"path": main[0], "symbol": main[1]} if main else None}
    test_files, orphans = [], []
    for path in sorted(files):
        if not is_test(path) or path in deleted or not path.endswith(".py"):
            continue
        mine = runs.get(path, [])
        changed = [n for n in (symbols.get(path) or {}).get("names") or [] if n.split(".")[-1].startswith("test")]
        whole = any(sym is None for _, sym in mine)
        named = {sym for _, sym in mine if sym}
        loose = [] if whole else [n for n in changed if not any(n == x or n.startswith(x + ".") or x.startswith(n + ".") for x in named)]
        if mine:
            test_files.append({"path": path, "file": short(path), "checks": sorted({vid for vid, _ in mine})})
        if loose:
            orphans.append({"path": path, "file": short(path), "tests": loose})
    n = sum(len(o["tests"]) for o in orphans)
    tests = {"files": test_files, "orphans": orphans, "orphan_tests": n,
             "summary": (f"{n} changed {'test backs' if n == 1 else 'tests back'} no claim." if n else "Each changed test backs a claim."),
             "action": "Link them to a claim, or delete them." if n else ""}
    return out, tests


# ---- The diff spine -----------------------------------------------------------------------

# The protection of a changed file, riskiest first. The guided review shows each file with its kind.
SPINE_KINDS = {
    "check": "No claim, risky: add a check", "ask": "No claim: ask for one", "read": "No claim: read it",
    "partial": "Covered in part", "protected": "Protected by {n}", "skim": "Low risk: skim",
    "test": "A test or a check", "other": "Docs, data or config", "deleted": "Deleted",
}
SPINE_RANK = {"check": 0, "ask": 1, "read": 2, "partial": 3, "protected": 4, "skim": 6, "test": 7, "other": 8, "deleted": 9}
# A file whose main change the guided review shows as code: the files that a reviewer must read.
SPINE_READ = ("check", "ask", "read", "partial", "protected")
# The reading order of the chapters of the change (explain.json change.chapters): the core change
# first, then the code that supports it, the wiring and config, the data, the docs; generated files
# and the tests come last.
TIERS = ["core", "supporting", "wiring", "data", "docs", "generated"]
FLAG_LEVELS = ("risk", "question", "nit")
WINDOW = 3


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


def _hunk_line(patch: str) -> int | None:
    """The first line that a control's patch changes, as a line of the file at the head."""
    old = None
    for row in patch.splitlines():
        m = re.match(r"@@ -(\d+)", row)
        if m:
            old = int(m.group(1))
            continue
        if old is None or row.startswith(("---", "+++")):
            continue
        if row.startswith("-"):
            return old
        if not row.startswith("+"):
            old += 1
    return None


def look_closely(data: dict, refs: dict, u: dict) -> list[dict]:
    """The "look closely" flags: each pinned to a line of a changed file at the head, each from a
    verified source and with the condition that triggers it. A verified bug (find-bugs) is a risk and
    a lead is a question; a check that cannot fail is a risk and one that missed its planted bug is a
    question, at the line that the bug changed; a changed file with risk and no claim is a risk when it
    touches money, safety or I/O and a question else, at its main change. No source, no flag."""
    import verdicts
    files = refs["diff"]["files"]
    by_key = {_key(r["ref"]): r for r in refs["refs"]}
    out: list[dict] = []
    for f in findings.collect(data):
        m = re.search(r"([\w./-]+\.\w+):(\d+)", f.get("ref") or "")
        if not m or m.group(1) not in files:
            continue
        out.append({"level": "risk" if f["status"] == "verified" else "question", "source": "bug", "path": m.group(1), "line": int(m.group(2)),
                    "text": capital(f["line"].replace(": the code does not do this", "")) + ": the code does not do this.",
                    "trigger": (f.get("trigger") or "").rstrip("?") or None})
    verifiers = {v["id"]: v for v in data["verifiers"]}
    for k in data["controls"]:
        v = verifiers.get(k["verifier"])
        if not v or verdicts.control_outcome(k) == "caught":
            continue
        result = onto.check_result(data, v)
        if result not in ("missed", "cannot-fail"):
            continue
        for e in (refs.get("controls") or {}).get(k["id"], [])[:1]:
            line = _hunk_line(e.get("patch") or "")
            if not line or e["path"] not in files:
                continue
            name = check_name(data, v)
            out.append({"level": "risk" if result == "cannot-fail" else "question", "source": "check", "path": e["path"], "line": line,
                        "text": (f"{capital(name)} passes on every planted bug, so it cannot protect this line." if result == "cannot-fail" else
                                 f"{capital(name)} still passed when we changed this line. It does not see this bug."),
                        "trigger": broke(k).rstrip(".")})
    for f in u["files"] + [x for x in u["core"] if not x["by"]["cited"]]:
        if not f["risks"] or not f.get("main"):
            continue
        r = by_key.get(_key(f["main"]))
        if not r:
            continue
        money = any(w.startswith("touches") for w in f["risks"])
        partly = f in u["core"]
        out.append({"level": "risk" if money else "question", "source": "unclaimed", "path": f["path"], "line": r["start"],
                    "text": (f"A check runs {f['role']}, but no claim says what it must do here. Read it, or ask the author for a claim." if partly
                             else f"No claim covers {f['role']}. {f['action']['text']}"),
                    "trigger": capital(", ".join(f["risks"]))})
    for x in out:
        x["ref"] = {"path": x["path"], "start": max(1, x["line"] - WINDOW), "end": x["line"] + WINDOW}
    order = {lv: i for i, lv in enumerate(FLAG_LEVELS)}
    return sorted(out, key=lambda x: (order[x["level"]], x["path"], x["line"]))


def spine(data: dict, refs: dict, extra: dict | None, coverage: dict | None, u: dict, rows: dict[str, dict]) -> dict:
    """Each changed file of the diff, grouped into the chapters of the change (explain.json
    change.chapters: one idea each, in reading order; a file goes to the chapter with its longest
    path or prefix), with the test files in an automatic Tests chapter (with their test names) and
    each changed non-test file that no chapter holds in `unassigned`. Without chapters, the change
    areas group the files. In each group, riskiest first: its line counts, its role, the claims that
    protect it (weakest first), its main changed symbol, its "look closely" flags and its protection:
    no claim (with the action of the unclaimed level), covered in part, protected by N claims, low
    risk, or deleted. The page shows these values; it does not compute them."""
    spec = (extra or {}).get("unclaimed") or {}
    change = (extra or {}).get("change") or {}
    chapters = change.get("chapters") or []
    areas = [a for a in change.get("areas") or [] if a.get("paths")]
    names_ = {a["id"]: a["name"] for a in change.get("areas") or []}
    diff = refs["diff"]
    files, deleted, created, symbols = diff["files"], set(diff["deleted"]), set(diff["created"]), diff.get("symbols") or {}
    by_key = {_key(r["ref"]): r for r in refs["refs"]}
    cited: dict[str, set[str]] = {}
    for c in data["claims"]:
        for ref in c.get("code", []):
            if _key(ref) in by_key:
                cited.setdefault(ref["path"], set()).add(c["id"])
    named, ran, edited = named_files(data, files), exercised_files(data, coverage, files), edited_files(data, files)
    loose = {f["path"]: f for f in u["files"]}
    partial = {f["path"]: f for f in u["core"]}
    root = diff_root(files)
    order = {v: i for i, v in enumerate(VERDICTS)}
    flags: dict[str, list[dict]] = {}
    for x in look_closely(data, refs, u):
        flags.setdefault(x["path"], []).append(x)

    def entries(ch: dict) -> list[str]:
        return [x if isinstance(x, str) else x["path"] for x in ch.get("files") or []]

    def chapter_of(path: str) -> dict | None:
        best = None
        for ch in chapters:
            for prefix in entries(ch):
                if _under(path, prefix) and (best is None or len(prefix) > best[0]):
                    best = (len(prefix), ch)
        return best[1] if best else None

    def area_of(path: str) -> dict | None:
        return next((a for a in areas if any(_under(path, x) for x in a["paths"])), None)

    groups: dict[str, dict] = {}
    clash = [ch["id"] for ch in chapters if ch["id"] in ("code", "test", "other", "deleted", "unassigned")]
    if clash:
        tm.fail("derive: explain.json change.chapters uses a reserved id: " + ", ".join(clash) + " (code, test, other, deleted and unassigned name the automatic chapters)", 1)
    if chapters:
        ranked = sorted(enumerate(chapters), key=lambda t: (TIERS.index(t[1].get("tier", "core")) if t[1].get("tier", "core") in TIERS else 0, t[0]))
        for _, ch in ranked:
            groups[ch["id"]] = {"id": ch["id"], "name": ch["title"], "tier": ch.get("tier", "core"), "explain": ch.get("explain") or [],
                                "note": ch.get("note"), "replaced_by": None, "files": []}
    else:
        for a in areas:
            groups[a["id"]] = {"id": a["id"], "name": a["name"], "tier": "core", "explain": [], "note": a.get("note"),
                               "replaced_by": {"id": a["replaced_by"], "name": names_.get(a["replaced_by"], a["replaced_by"])} if a.get("replaced_by") else None,
                               "files": []}
    rest = {"code": ("Other changed code", "supporting"), "test": ("Tests", "tests"), "other": ("Docs, data and config", "docs"),
            "deleted": ("Other deleted files", "data"), "unassigned": ("Files that no chapter holds", "supporting")}
    unassigned = []
    for path, (plus, minus) in files.items():
        claims = sorted(set().union(cited.get(path, set()), named.get(path, set()), ran.get(path, set()), edited.get(path, set())),
                        key=lambda cid: (-order.get(rows[cid]["strength"], 0), cid))
        if path in deleted:
            kind, text = "deleted", None
        elif path in loose:
            kind, text = loose[path]["action"]["kind"], loose[path]["action"]["text"]
        elif path in partial:
            kind, text = "partial", partial[path]["action"]["text"]
        elif is_test(path):
            kind, text = "test", None
        elif not is_code(path):
            kind, text = "other", None
        elif claims:
            kind, text = "protected", None
        else:
            kind, text = "skim", "Low risk: skim." if plus else "It only removes lines."
        label = SPINE_KINDS[kind].format(n=f"{len(claims)} {'claim' if len(claims) == 1 else 'claims'}")
        test = is_test(path)
        if chapters:
            ch = chapter_of(path)
            # A test file joins a chapter only when the chapter names it by its own path: the test is the change.
            if ch and test and path not in entries(ch):
                ch = None
            gid = ch["id"] if ch else ("test" if test else "unassigned")
            if gid == "unassigned":
                unassigned.append(path)
        else:
            area = area_of(path)
            gid = area["id"] if area else ("deleted" if kind == "deleted" else kind if kind in ("test", "other") else "code")
        if gid not in groups:
            groups[gid] = {"id": gid, "name": rest[gid][0], "tier": rest[gid][1], "explain": [], "note": None, "replaced_by": None, "files": []}
        main = (symbols.get(path) or {}).get("main")
        weakest_rank = order.get(rows[claims[0]]["strength"], 0) if claims else 0
        entry = {
            "path": path, "file": path[len(root):] if root and path.startswith(root) else path, "added": plus, "removed": minus,
            "created": path in created, "deleted": path in deleted,
            "role": (spec.get("roles") or {}).get(path) or (humanize(path) if is_code(path) else None),
            "note": (spec.get("notes") or {}).get(path), "main": main, "claims": claims, "flags": flags.get(path, []),
            # GitHub's anchor for the file in the PR's files view: the SHA-256 of the path.
            "diff": hashlib.sha256(path.encode()).hexdigest(),
            "status": {"kind": kind, "label": label, "text": text},
            "_rank": (SPINE_RANK[kind] - (weakest_rank / 10 if kind == "protected" else 0), -(plus + minus), path)}
        if test:
            entry["tests"] = [n for n in (symbols.get(path) or {}).get("names") or [] if n.split(".")[-1].startswith("test")]
        groups[gid]["files"].append(entry)
    out = []
    ids = [*groups.keys()]
    # The automatic chapters: the unassigned files right after the chapters, the tests last.
    tail = [g for g in ("code", "other", "deleted", "unassigned") if g in ids] + (["test"] if "test" in ids else [])
    for gid in [g for g in ids if g not in tail] + tail:
        g = groups[gid]
        if not g["files"]:
            continue
        # A chapter keeps the reading order of its files as the explain step listed them; an automatic group goes riskiest first.
        listed = {p: i for i, p in enumerate(entries(next((c for c in chapters if c["id"] == gid), {})))}
        g["files"].sort(key=lambda f: (min([i for p, i in listed.items() if _under(f["path"], p)] or [len(listed)]), f["_rank"]))
        for f in g["files"]:
            f.pop("_rank")
        g["added"] = sum(f["added"] for f in g["files"])
        g["removed"] = sum(f["removed"] for f in g["files"])
        g["unclaimed"] = sum(1 for f in g["files"] if f["status"]["kind"] in ("check", "ask", "read"))
        g["flags"] = sum(len(f["flags"]) for f in g["files"])
        g["reviewable"] = g["tier"] not in ("tests", "generated")
        out.append(g)
    allf = [f for g in out for f in g["files"]]
    # How the changed files connect: the imports between them (explain.py), as links between chapters.
    owner = {f["path"]: g["id"] for g in out for f in g["files"]}
    weight: dict[tuple[str, str], int] = {}
    for a_, b_ in diff.get("imports") or []:
        x, y = owner.get(a_), owner.get(b_)
        if x and y and x != y:
            weight[(x, y)] = weight.get((x, y), 0) + 1
    links = [{"from": x, "to": y, "n": n} for (x, y), n in sorted(weight.items())]
    claimed = sum(1 for f in allf if f["status"]["kind"] == "protected")
    half = sum(1 for f in allf if f["status"]["kind"] == "partial")
    line = f"{claimed} of {len(allf)} changed files have a claim that protects them, and claims cover {half} more in part."
    nflags = sum(len(f["flags"]) for f in allf)
    return {"groups": out, "files": len(allf), "protected": claimed, "partial": half, "summary": line, "unassigned": unassigned,
            "flags": nflags, "github": [f["path"] for f in sorted(allf, key=lambda f: f["path"])], "links": links}


# ---- Bugs found ----------------------------------------------------------------------------

def bugs(data: dict) -> list[dict]:
    """Each possible bug of an invariant (findings.collect), verified bugs first, in the find-bugs
    heading format, with its detail lines."""
    rows = [{"heading": text[0], "lines": text[1:], "verified": f["status"] == "verified"}
            for f in findings.collect(data) for text in [findings.render(f, indent="")]]
    return sorted(rows, key=lambda r: not r["verified"])


# ---- All of it -----------------------------------------------------------------------------

def derive(data: dict, refs: dict, extra: dict | None = None, ready: dict | None = None, coverage: dict | None = None,
           cfg: dict | None = None) -> dict:
    """The derived block of refs.resolved.json. `coverage` is the coverage record of the run
    ({check id: [paths]}); without it, only the code refs, the claim texts and the control edits count."""
    if ready and ready.get("head") != data["head"]:
        ready = None
    u = unclaimed(data, refs, (extra or {}).get("unclaimed"), coverage)
    risky = sum(1 for f in u["files"] if f["risks"])
    form, items = merge_verdict(data, ready, risky, cfg)
    accept = merge_items(data, ready, risky, cfg)[1]
    checks = checks_view(data, refs, claim_rows(data, extra, cfg))
    verdict_of = {c["id"]: c["verdict"] for c in data["claims"]}
    rows = claim_rows(data, extra, cfg)
    promises = [{"id": p["id"], "strength": s, "claims": cids, "count": len(cids), "tally": tally([verdict_of[c] for c in cids]),
                 "bars_met": sum(1 for c in cids if rows[c]["bar"]["met"]),
                 "tier": max([t for c in data["claims"] if c["id"] in cids for t in [c.get("tier")] if t] or [0]) or None}
                for p, s, cids in promises_in_order(data)]
    return {"schema": SCHEMA, "head": data["head"], "promises": promises, "claims": rows, "bars": bars_summary(data, rows),
            "verify": verify(data, promises, extra),
            "merge": {"form": form, "items": items, "blockers": len(items) if form == "not-ready" else 0, "accept": accept},
            "ready": ready, "unclaimed": u, "risky_unclaimed": risky, "bugs": bugs(data),
            "spine": spine(data, refs, extra, coverage, u, rows), "checks": checks[0], "tests": checks[1]}


def load_coverage(path: Path | None, head: str) -> dict | None:
    """The coverage record (coverage.json of the run) at this head: {check id: [paths]}; None without one."""
    if not path or not Path(path).is_file():
        return None
    body = tm.load(path)
    return {vid: row["files"] for vid, row in (body.get("checks") or {}).items()} if body.get("head") == head else None


def risky_unclaimed(run: Path | None, data: dict) -> int:
    """The risky unclaimed count of the last explain build of the run (refs.resolved.json at the
    map head), so a merge verdict outside the page counts the same risks; 0 without a build."""
    p = Path(run) / "refs.resolved.json" if run else None
    if not p or not p.is_file():
        return 0
    body = tm.load(p)
    d = body.get("derived") or {}
    return d.get("risky_unclaimed", 0) if d.get("head") == data.get("head") else 0
