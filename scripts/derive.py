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
               accept) or "ready"
  unclaimed    the changed source files outside the claims, with their risk and one action, the
               core files that claims cover in part, and the summary lines (risky files first)
  bugs         the possible bugs of the invariants, in the find-bugs heading format (findings.py)

A file is covered when a claim's code refs cite it, when a claim names it, when one of the
claim's checks exercises it (the coverage record of the run: `understando coverage`), or when a
control of one of its checks edits it.
"""

from __future__ import annotations

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


def merge_verdict(data: dict, ready: dict | None = None, risky_unclaimed: int = 0) -> tuple[str, list[dict]]:
    """Can the reviewer merge? A promise at Gap or Asserted with a reviewer action blocks, unless
    each of its weak claims is waived; a failed ready gate blocks; a Backed promise with a reviewer
    action, a waived claim and changed code with risk and no claim are risks to accept.
    Returns ("not-ready" | "accept" | "ready", items); each item has label, text and href."""
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
    if risky_unclaimed:
        n = risky_unclaimed
        accept.append({"label": "Unclaimed changes", "text": f"{n} changed {'file has' if n == 1 else 'files have'} risk and no claim. Read {'it' if n == 1 else 'them'} before you approve.",
                       "href": "#unclaimed"})
    if blocking:
        return "not-ready", blocking
    return ("accept", accept) if accept else ("ready", [])


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
    import verdicts
    mine = [k for k in data["controls"] if k["verifier"] == v["id"] and verdicts.control_outcome(k) != "caught"]
    for k in mine:
        for o in data["controls"]:
            if o["verifier"] != v["id"] and verdicts.control_outcome(o) == "caught" and o.get("edits") == k.get("edits"):
                return next(x for x in data["verifiers"] if x["id"] == o["verifier"])
    return None


def check_action(data: dict, v: dict, claim: dict, result: str, fix: str | None) -> str:
    """One reviewer action for a check, in plain words."""
    if result == "caught":
        return "No action: it caught its planted bug."
    if result == "none":
        base = ("Only the PR text states it. Add a check (understando close), or accept the risk." if claim.get("stated")
                else "No check exists, and the PR text does not state it. Decide if it matters; to close it, add a check (understando close).")
        return base + (f" The cheapest fix: {fix}" if fix else "")
    if result == "missed":
        other = same_bug_catcher(data, v)
        if other:
            return f"Trust {check_name(data, other)}, not this check."
    if result == "recorded" and v.get("tier") == "guess":
        return "Treat it as one opinion. Ask a model of another family to check it, or read the evidence yourself."
    if result == "recorded" and (v.get("formal_record") or {}).get("formal", {}).get("verdict") not in (None, "Formal"):
        return "Its formal record is not Formal yet. Finish its conformance run (understando formalize)."
    if v.get("formal_record") and (v["formal_record"].get("formal") or {}).get("verdict") != "Formal":
        return "Its formal record is not Formal yet. Finish its conformance run (understando formalize)."
    base = {"missed": "Add a check that fails on this bug, or fix this check so that it does.",
            "cannot-fail": "Fix this check so that it can fail, or replace it (understando close).",
            "broken": "Fix this check: it fails or does not complete at the PR head.",
            "no-bug": "Plant a bug for this check (understando probe), or accept the claim as it stands.",
            "recorded": "It is a record of a past run. Run it again, or accept the record as it stands.",
            "checked": "Plant a bug for this mechanical check, or add a CI rule that keeps it true."}[result]
    return base + (f" The cheapest fix: {fix}" if fix and result != "recorded" else "")


def claim_rows(data: dict, explain: dict | None = None) -> dict[str, dict]:
    """Each claim: its strength (its weakest check), its checks with their strength and result, the
    summary line ("5 checks: 4 caught their bug, 1 missed.") and the weakest check with its action."""
    fx = fixes(data, explain)
    out = {}
    for c in data["claims"]:
        checks = onto.checks_of(data, c)
        rows = [{"id": v["id"], "name": check_name(data, v), "kind": v["kind"], "strength": onto.check_strength(data, v, c),
                 "result": onto.check_result(data, v)} for v in checks]
        tools = [r for r in rows if r["kind"] != "none"]
        counts = {r: sum(1 for x in tools if x["result"] == r) for r in onto.RESULTS if any(x["result"] == r for x in tools)}
        order = ["caught", "missed", "cannot-fail", "broken", "no-bug", "recorded", "checked"]
        parts = [f"{counts[r]} {(RESULT_ONE if counts[r] == 1 and r not in ('caught',) else RESULT_WORDS)[r]}" for r in order if r in counts]
        if len(tools) == 1:
            summary = f"1 check: it {RESULT_ONE[tools[0]['result']]}."
        elif tools:
            summary = f"{len(tools)} checks: {', '.join(parts)}."
        else:
            summary = "No check: only the PR text states it." if c.get("stated") else "No check, and the PR text does not state it."
        weak, strength = onto.weakest_check(data, c)
        w = None
        if weak:
            result = onto.check_result(data, weak)
            name = check_name(data, weak)
            said = {"caught": f"The weakest check is {name}. It caught its planted bug.",
                    "missed": f"The weakest check is {name}. It missed its planted bug.",
                    "cannot-fail": f"The weakest check is {name}. It cannot fail: it passed on each planted bug.",
                    "broken": f"The weakest check is {name}. It fails or does not complete at the PR head.",
                    "no-bug": f"The weakest check is {name}. No planted bug ran, so no run proved that it can fail.",
                    "recorded": f"The weakest check is {name}. It is a record of a past run, and we did not run it again.",
                    "checked": f"The weakest check is {name}. It is a mechanical check with no planted bug.",
                    "none": "No tool checks this claim. Only the PR text states it." if c.get("stated") else
                            "No tool checks this claim, and the PR text does not state it."}[result]
            if strength == "Backed" and not onto.intent(data, c) and onto.check_strength(data, weak, {**c, "stated": True, "parts": None}) != "Backed":
                said += " The claim stays Backed: the PR does not state each part, and no invariant that the user confirmed backs it."
            action = check_action(data, weak, c, result, fx.get(c["id"]))
            import verdicts
            bug = next((b for b in (verdicts.disagreeing(data, i) for i in onto.invariants_of(c)) if b), None)
            if bug:
                said = (f"The code disagrees with a rule that the user confirmed: {names.of(data, bug['id'])}. " + said)
                action = "Do not trust this claim until the fix lands: see the bugs found." + (" Then " + action[0].lower() + action[1:] if result != "caught" else "")
            w = {"id": weak["id"], "name": name, "result": result, "strength": strength, "text": said, "action": action}
        out[c["id"]] = {"strength": c.get("verdict") or strength, "tier": c.get("tier"), "checks": rows, "n": len(tools),
                        "counts": counts, "summary": summary, "weakest": w}
    return out


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
        weak.append({"check": v["id"], "control": k["id"], "name": check_name(data, v), "broke": broke(k), "happened": happened, "why": why,
                     "action": action, "ids": " · ".join([k["id"], v["id"], *[c["id"] for c in own]])})
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
    return {"result": line, "other": other, "tone": tone, "checks": len(tools), "ran": len(ran), "caught": len(caught),
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
        if is_core(path) and claims:
            text = ("Read the lines that no claim cites." if share else
                    "A check runs it or a claim names it, but no claim cites its lines. Read the lines that no claim cites.")
            core_rows.append({**base, "risks": [], "action": {"kind": "read", "text": text}})
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
    core_rows.sort(key=lambda f: (f["cited"] / max(f["total"], 1), f["path"]))
    out = [r for r, _ in rows]
    return {"files": out, "core": core_rows, "summary": unclaimed_summary(out)}


def unclaimed_summary(files: list[dict]) -> dict:
    """The risky files first: "12 risky files have no claim. Read these first." Then a quieter line
    with the count of the other files."""
    risky = sum(1 for f in files if f["risks"])
    rest = len(files) - risky
    if not files:
        return {"risky": 0, "rest": 0, "lead": "Each changed source file has a claim.", "quiet": ""}
    lead = (f"{risky} risky {'file has' if risky == 1 else 'files have'} no claim. Read {'it' if risky == 1 else 'these'} first." if risky
            else "No risky file is without a claim.")
    quiet = (f"{rest} other changed {'file has' if rest == 1 else 'files have'} no claim. {'It is' if rest == 1 else 'They are'} low risk: skim {'it' if rest == 1 else 'them'}."
             if rest else "")
    return {"risky": risky, "rest": rest, "lead": lead, "quiet": quiet}


def _key(ref: dict) -> tuple:
    return tuple(sorted((k, repr(v)) for k, v in ref.items() if k != "note"))


# ---- Bugs found ----------------------------------------------------------------------------

def bugs(data: dict) -> list[dict]:
    """Each possible bug of an invariant (findings.collect), verified bugs first, in the find-bugs
    heading format, with its detail lines."""
    rows = [{"heading": text[0], "lines": text[1:], "verified": f["status"] == "verified"}
            for f in findings.collect(data) for text in [findings.render(f, indent="")]]
    return sorted(rows, key=lambda r: not r["verified"])


# ---- All of it -----------------------------------------------------------------------------

def derive(data: dict, refs: dict, extra: dict | None = None, ready: dict | None = None, coverage: dict | None = None) -> dict:
    """The derived block of refs.resolved.json. `coverage` is the coverage record of the run
    ({check id: [paths]}); without it, only the code refs, the claim texts and the control edits count."""
    if ready and ready.get("head") != data["head"]:
        ready = None
    u = unclaimed(data, refs, (extra or {}).get("unclaimed"), coverage)
    risky = sum(1 for f in u["files"] if f["risks"])
    form, items = merge_verdict(data, ready, risky)
    verdict_of = {c["id"]: c["verdict"] for c in data["claims"]}
    promises = [{"id": p["id"], "strength": s, "claims": cids, "count": len(cids), "tally": tally([verdict_of[c] for c in cids])}
                for p, s, cids in promises_in_order(data)]
    return {"schema": SCHEMA, "head": data["head"], "promises": promises, "claims": claim_rows(data, extra),
            "verify": verify(data, promises, extra),
            "merge": {"form": form, "items": items, "blockers": len(items) if form == "not-ready" else 0},
            "ready": ready, "unclaimed": u, "risky_unclaimed": risky, "bugs": bugs(data)}


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
