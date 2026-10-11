"""The review ontology: promise -> claim -> check.

  promise  what the PR guarantees, in plain words                        3 to 6 for each PR
  claim    one statement that a reviewer accepts or rejects              about 2 to 5 for each
                                                                         promise, 10 to 25 in all
  check    one verifier with its controls: a test, a type pin, an import as many as needed
           rule, a Lean theorem, a TLA+ model, an eval record or a model
           judgment

Shape 2 (schema_version 2): each claim lists its checks in `checks`. Each verifier is a check, and
its `claims` list mirrors the claims that list it (`sync`). Shape 1 links each verifier to its
claims only; `upgrade` reads it, for one release. A claim with no tool check lists one check of
kind `none`: the PR text alone (Asserted), or nothing (Gap).

Strength. The strength of a check is the verdict that the check alone gives its claim. The
strength of a claim is the strength of its weakest check, and the claim card names that check
with its action. The strength of a promise is the strength of its weakest claim.

Merge rule (`group_lint`). Two claims become one claim with more checks when they have the same
promise, the same kind of check and the same reviewer action, and a reviewer accepts or rejects
them together. A risky surface (safety, money, the editor's anti-gaming rules, clinical output,
production) keeps its own claim.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import tm  # noqa: E402

SHAPE = 2
VERDICTS = ["Formal", "Proven", "Backed", "Asserted", "Gap"]
DEAD = ("cannot-fail", "failing", "broken", "stale")
COUNTED = ("proven", "untested", "recorded", "checked")
BUDGET = {"promises": (3, 6), "per_promise": (2, 5), "claims": (10, 25)}


# ---- The shape ---------------------------------------------------------------------------------

def is_tool(v: dict) -> bool:
    return v.get("kind") != "none"


def checks_of(data: dict, claim: dict | str) -> list[dict]:
    """The checks of a claim: `claims[].checks` (shape 2), else each verifier that names the claim (shape 1)."""
    if isinstance(claim, str):
        claim = next((c for c in data.get("claims", []) if c["id"] == claim), {"id": claim})
    if claim.get("checks"):
        vs = {v["id"]: v for v in data.get("verifiers", [])}
        return [vs[i] for i in claim["checks"] if i in vs]
    return [v for v in data.get("verifiers", []) if claim["id"] in v.get("claims", [])]


def claims_of(data: dict, v: dict) -> list[dict]:
    """The claims that a check backs, in either shape."""
    return [c for c in data.get("claims", []) if any(x["id"] == v["id"] for x in checks_of(data, c))]


def invariants_of(claim: dict) -> list[str]:
    return list(claim.get("invariants") or ([claim["invariant"]] if claim.get("invariant") else []))


def confirmed(data: dict, inv_id: str) -> bool:
    return any(i["id"] == inv_id and i["author"] == "user" and i["status"] == "accepted" for i in data.get("invariants", []))


def intent(data: dict, claim: dict) -> bool:
    """Proven and Formal need intent: the PR states the claim, or the user confirmed each of its
    invariants. A merged claim needs intent for each part, so a merge never lends intent to a part
    that has none."""
    parts = claim.get("parts") or []
    if parts and any("stated" in x or "invariant" in x for x in parts):
        return all(x.get("stated") or (x.get("invariant") and confirmed(data, x["invariant"])) for x in parts)
    invs = invariants_of(claim)
    return bool(claim.get("stated")) or (bool(invs) and all(confirmed(data, i) for i in invs))


def next_id(data: dict, prefix: str) -> str:
    items = {"C": data["claims"], "V": data["verifiers"], "K": data["controls"]}[prefix]
    n = max([int(i["id"][1:]) for i in items if i["id"][1:].isdigit()] + [0]) + 1
    return f"{prefix}{n:02d}"


def none_check(data: dict, claim: dict) -> dict:
    stated = bool(claim.get("stated"))
    return {"id": next_id(data, "V"), "kind": "none", "claims": [claim["id"]], "tier": "guess",
            "name": "the PR text alone" if stated else "no check yet",
            "description": ("No tool checks this claim. Only the PR text states it." if stated
                            else "No tool checks this claim, and the PR text does not state it."),
            "independence": {"by": "human"}, "cost": {"usd": 0},
            "provenance": "understando map: a placeholder until a check exists (understando close)."}


def sync(data: dict) -> None:
    """Shape 2: each verifier's `claims` list is the claims that list it."""
    by: dict[str, list[str]] = {}
    for c in data["claims"]:
        for vid in c.get("checks") or []:
            by.setdefault(vid, []).append(c["id"])
    for v in data["verifiers"]:
        v["claims"] = by.get(v["id"], [])


def upgrade(data: dict) -> int:
    """Write the map in shape 2. Shape 1 links each verifier to its claims; each claim now lists its
    checks. A claim with no tool check gets one check of kind none; a claim with a tool check loses
    its none check. Returns the number of changes. Idempotent."""
    n = 0
    if data.get("schema_version") != SHAPE:
        data["schema_version"] = SHAPE
        n += 1
    for c in data["claims"]:
        if not c.get("checks"):
            c["checks"] = [v["id"] for v in data["verifiers"] if c["id"] in v.get("claims", [])]
            n += 1
    vs = {v["id"]: v for v in data["verifiers"]}
    drop = set()
    for c in data["claims"]:
        tools = [i for i in c["checks"] if i in vs and is_tool(vs[i])]
        # A none check stays while it is the only evidence of a part.
        keep = {i for p in c.get("parts") or [] for i in (p.get("checks") or [])
                if p.get("checks") and not any(j in vs and is_tool(vs[j]) for j in p["checks"])}
        if keep:
            tools = [i for i in c["checks"] if i in tools or i in keep]
        if tools and len(tools) != len(c["checks"]):
            drop |= {i for i in c["checks"] if i in vs and not is_tool(vs[i])}
            c["checks"] = tools
            n += 1
        if not c["checks"]:
            v = none_check(data, c)
            data["verifiers"].append(v)
            vs[v["id"]] = v
            c["checks"] = [v["id"]]
            n += 1
    if drop:
        data["verifiers"] = [v for v in data["verifiers"] if v["id"] not in drop or any(v["id"] in c["checks"] for c in data["claims"])]
    sync(data)
    return n


def reconcile(data: dict) -> None:
    """Shape 2, before a save: a verb that links a verifier to a claim through `verifier.claims`
    (import, trim, formalize) also puts it in `claims[].checks`. A check that no longer exists
    leaves the claim. Then the none checks and the mirror follow (upgrade)."""
    if data.get("schema_version") != SHAPE:
        return
    vids = [v["id"] for v in data.get("verifiers", [])]
    for c in data.get("claims", []):
        linked = [v["id"] for v in data["verifiers"] if c["id"] in v.get("claims", [])]
        c["checks"] = [x for x in dict.fromkeys([*(c.get("checks") or []), *linked]) if x in vids]
    upgrade(data)


def shape_errors(data: dict) -> list[str]:
    """Shape 2 rules: each claim lists checks that exist, each check backs a claim, and the
    verifier lists mirror the claim lists."""
    if data.get("schema_version") != SHAPE:
        return []
    errors = []
    vids = {v["id"] for v in data["verifiers"]}
    listed: dict[str, list[str]] = {}
    for c in data["claims"]:
        if not c.get("checks"):
            errors.append(f"claim {c['id']}: has no checks; list its checks, or run understando map, which adds a check of kind none")
        for vid in c.get("checks") or []:
            if vid not in vids:
                errors.append(f"claim {c['id']}: unknown check {vid}")
            listed.setdefault(vid, []).append(c["id"])
    for v in data["verifiers"]:
        if v["id"] not in listed:
            errors.append(f"check {v['id']}: no claim lists it; put it under a claim, or delete it")
        elif sorted(v.get("claims", [])) != sorted(listed[v["id"]]):
            errors.append(f"check {v['id']}: its claims {v.get('claims')} differ from the claims that list it {listed[v['id']]}; run understando map")
    return errors


# ---- Strength ----------------------------------------------------------------------------------

def check_strength(data: dict, v: dict, claim: dict) -> str:
    """The verdict that this check alone gives its claim (references/verdicts.md)."""
    import verdicts
    if not is_tool(v) or v.get("state") in DEAD:
        return "Asserted" if claim.get("stated") else "Gap"
    if v.get("state") == "proven" and verdicts.can_prove(v, data.get("author_family")):
        best = "Formal" if (tm.ladder(v) or 0) >= 4 else "Proven"
        return best if intent(data, claim) else "Backed"
    if v.get("state") in COUNTED:
        return "Backed"
    return "Asserted" if claim.get("stated") else "Gap"


def weaker(a: str, b: str) -> str:
    return max(a, b, key=VERDICTS.index)


# The result of one check on its planted bugs, worst first.
RESULTS = ["none", "broken", "cannot-fail", "missed", "no-bug", "checked", "recorded", "caught"]


def check_result(data: dict, v: dict) -> str:
    """caught: each planted bug made it fail. missed: one did not. cannot-fail: it passed on each one.
    no-bug: no planted bug ran. recorded or checked: a past run or a mechanical check, with no planted bug.
    broken: it fails or does not complete at the head. none: no tool check."""
    import verdicts
    if not is_tool(v):
        return "none"
    state = v.get("state")
    if state == "cannot-fail":
        return "cannot-fail"
    if state in ("failing", "broken", "stale"):
        return "broken"
    ran = [verdicts.control_outcome(k) for k in data["controls"] if k["verifier"] == v["id"]]
    ran = [o for o in ran if o in ("caught", "missed")]
    if ran:
        return "caught" if all(o == "caught" for o in ran) else "missed"
    return state if state in ("recorded", "checked") else "no-bug"


def parts_of(data: dict, claim: dict) -> list[dict]:
    """The statements of a claim, each with its own checks: [{id, text, stated, invariants, checks}].
    A claim with no `parts` is one part. A part with no `checks` list has all the claim's checks."""
    checks = checks_of(data, claim)
    rows = claim.get("parts") or []
    if not rows:
        return [{"id": claim["id"], "text": claim.get("text", ""), "stated": bool(claim.get("stated")),
                 "invariants": invariants_of(claim), "checks": checks}]
    by = {v["id"]: v for v in checks}
    out = []
    for p in rows:
        ids = p.get("checks")
        own = [by[i] for i in ids if i in by] if ids is not None else checks
        if ids is not None and not own:
            own = [v for v in checks if not is_tool(v)]
        invs = [p["invariant"]] if p.get("invariant") else ([] if "stated" in p else invariants_of(claim))
        out.append({"id": p.get("id") or claim["id"], "text": p.get("text", ""), "stated": bool(p.get("stated", claim.get("stated"))),
                    "invariants": invs, "checks": own})
    return out


def part_strength(data: dict, part: dict) -> tuple[str, dict | None]:
    """The strength of a part: its strongest check (a check whose control caught its bug, or a
    record with its result). Extra checks never lower a part. A possible bug of its invariant makes it Gap."""
    import verdicts
    pc = {"stated": part["stated"], "invariants": part["invariants"]}
    if any(verdicts.disagreeing(data, i) for i in part["invariants"]):
        best = min(part["checks"], key=lambda v: VERDICTS.index(check_strength(data, v, pc)), default=None)
        return "Gap", best
    if not part["checks"]:
        return ("Asserted" if part["stated"] else "Gap"), None
    best = min(part["checks"], key=lambda v: (VERDICTS.index(check_strength(data, v, pc)), -RESULTS.index(check_result(data, v))))
    return check_strength(data, best, pc), best


def claim_strength(data: dict, claim: dict) -> tuple[str, dict | None, dict | None]:
    """(strength, weakest part, its strongest check): a claim is as strong as its weakest part."""
    rows = [(part_strength(data, p), p) for p in parts_of(data, claim)]
    (strength, check), part = max(rows, key=lambda r: VERDICTS.index(r[0][0]))
    return strength, part, check


def weakest_check(data: dict, claim: dict) -> tuple[dict | None, str | None]:
    """The evidence of the weakest part: its strongest check, with the claim's strength."""
    strength, _, check = claim_strength(data, claim)
    return check, strength


def flagged(data: dict, claim: dict) -> list[dict]:
    """The checks that missed their planted bug, cannot fail or fail at the head. They are a warning:
    they lower a part only when they are its only evidence."""
    return [v for v in checks_of(data, claim) if is_tool(v) and check_result(data, v) in ("missed", "cannot-fail", "broken")]


# ---- Surfaces and their evidence bars ---------------------------------------------------------

SURFACES = ("frontend", "backend", "llm", "other")
FRONTEND = re.compile(r"(?i)\.(tsx|jsx|css|scss|html|vue|svelte)$|(^|/)(routes|pages)/")
# llm: the claim is about the quality or the behaviour of model output: an eval outcome, the
# agreement of a judge or of labellers, a gaming audit of edits. Code that handles model output
# (a gate, a confirmation rule, a refusal, a wiring path) is backend.
LLM_WORDS = re.compile(r"(?i)\b(evals?|labell?ers?|labell?ed|blind|non-inferior\w*|agreement|agree|failures? (per|for each)|"
                       r"gaming audit|audit found|scor(e|es|ed) (higher|lower|better|worse)|better than production|as good as)\b")
UI_WORDS = re.compile(r"(?i)\b(page|screen|button|browser|the user sees|shows the user|form|click\w*|ui)\b")
# The bar for each surface and risk. understando.toml [bars] can change it.
BARS = {"frontend": {"risky": "video", "normal": "video"}, "backend": {"risky": "formal", "normal": "property"},
        "llm": {"risky": "degraded-eval", "normal": "degraded-eval"}, "other": {"risky": "check", "normal": "check"},
        "unsure": {"risky": "formal", "normal": "property"}}
BAR_WORDS = {"video": "browser video", "e2e": "browser e2e", "formal": "proof", "static": "types or static rules",
             "property": "property test or static rule", "test": "a test", "degraded-eval": "eval with a degraded control",
             "eval": "eval", "check": "a check"}
LEVEL_RUNG = {"formal": 4, "static": 3, "property": 2, "test": 1}


def _claim_words(claim: dict) -> str:
    return " ".join([claim.get("text", ""), (claim.get("plain") or {}).get("what", ""), *[p.get("text", "") for p in claim.get("parts") or []]])


def surfaces(data: dict, claim: dict) -> list[str]:
    """The surface signals of a claim, by what it asserts. llm: an eval or a model judgment backs it,
    or its words are about the quality of model output. frontend: it cites UI code (TSX, JSX, CSS,
    HTML, a UI route). backend: it cites other code. No signal: other."""
    out = []
    kinds = {v["kind"] for v in checks_of(data, claim)}
    if kinds & {"eval", "model"} or LLM_WORDS.search(CODEY.sub(" ", _claim_words(claim))):
        out.append("llm")
    for r in claim.get("code") or []:
        out.append("frontend" if FRONTEND.search(r["path"]) else "backend")
    return list(dict.fromkeys(out)) or ["other"]


def surface(data: dict, claim: dict) -> str:
    """The surface of a claim: the user's `surface`, else the one that its signals agree on.
    Signals that conflict give `unsure`, and the review asks the user once:
      - an eval or a model judgment backs it: llm (frontend code too: unsure);
      - its words are about model output, but only code checks back it: unsure;
      - frontend and backend code: frontend when its words name a UI behaviour, else unsure."""
    if claim.get("surface") in SURFACES:
        return claim["surface"]
    found = surfaces(data, claim)
    strong_llm = bool({v["kind"] for v in checks_of(data, claim)} & {"eval", "model"})
    if "llm" in found:
        if strong_llm:
            return "unsure" if "frontend" in found else "llm"
        return "unsure" if ("backend" in found or "frontend" in found) else "llm"
    if "frontend" in found and "backend" in found:
        return "frontend" if UI_WORDS.search(_claim_words(claim)) else "unsure"
    return found[0]


def risky(claim: dict) -> bool:
    return bool(claim["risk"]) if "risk" in claim else bool(risk_tags(claim))


def eval_degraded(v: dict) -> bool:
    """A degraded variant of the eval scored measurably worse: the eval can fail."""
    d = (v.get("eval") or {}).get("degraded") or {}
    if "score" not in d or "baseline" not in d:
        return False
    return d["score"] > d["baseline"] if d.get("better") == "lower" else d["score"] < d["baseline"]


def meets(data: dict, part: dict, level: str) -> bool:
    pc = {"stated": part["stated"], "invariants": part["invariants"]}
    for v in part["checks"]:
        if not is_tool(v):
            continue
        caught = check_result(data, v) == "caught" or v.get("state") == "proven"
        if level == "video" and v["kind"] == "e2e" and caught and (v.get("artifact") or {}).get("video"):
            return True
        if level == "e2e" and v["kind"] == "e2e" and caught:
            return True
        if level in LEVEL_RUNG and check_strength(data, v, pc) in ("Formal", "Proven") and (tm.ladder(v) or 0) >= LEVEL_RUNG[level]:
            if level != "formal" or check_strength(data, v, pc) == "Formal":
                return True
        if level == "degraded-eval" and v["kind"] == "eval" and "recorded" in v and eval_degraded(v):
            return True
        if level == "eval" and v["kind"] == "eval" and "recorded" in v:
            return True
        if level == "check" and check_strength(data, v, pc) in ("Formal", "Proven", "Backed"):
            return True
    return False


def below_reason(data: dict, part: dict, level: str) -> str:
    tools = [v for v in part["checks"] if is_tool(v)]
    pc = {"stated": part["stated"], "invariants": part["invariants"]}
    proven = [v for v in tools if check_strength(data, v, pc) in ("Formal", "Proven")]
    if not tools:
        return "no check"
    if level in ("video", "e2e"):
        if any(v["kind"] == "e2e" for v in proven):
            return "an e2e run with no recorded video"
        return "only unit or component tests" if proven else "no browser e2e"
    if level in LEVEL_RUNG:
        rung = max([tm.ladder(v) or 0 for v in proven] or [0])
        formal = [v for v in tools if (tm.ladder(v) or 0) >= 4]
        if formal and level == "formal":
            if any(v.get("formal_record") and (v["formal_record"].get("formal") or {}).get("verdict") != "Formal" for v in formal):
                return "the proof or model has no passing formal record yet"
            if all(check_result(data, v) != "caught" for v in formal):
                return "no planted bug broke the proof or model"
            return "the proof or model has no passing conformance link"
        return ("only example tests" if rung == 1 else f"only {LADDER_WORDS.get(rung, 'checks')}" if rung else
                "no check caught a planted bug")
    if level in ("degraded-eval", "eval"):
        evals = [v for v in tools if v["kind"] == "eval"]
        if evals:
            return "the eval cannot show it can fail: no degraded variant ran"
        if any(v["kind"] == "model" for v in tools):
            return "only a model judgment, no eval"
        return "only tests, no eval"
    return "no check backs it"


LADDER_WORDS = {1: "example tests", 2: "property tests", 3: "types or static rules", 4: "a model check", 5: "a proof"}


def bar(data: dict, claim: dict, cfg: dict | None = None) -> dict:
    """The evidence bar of a claim and whether each part meets it:
    {surface, surfaces, mixed, risky, level, need, met, why, part, text}."""
    surf = surface(data, claim)
    found = surfaces(data, claim)
    kind = "risky" if risky(claim) else "normal"
    level = (((cfg or {}).get("bars") or {}).get(surf) or {}).get(kind) or BARS[surf][kind]
    rows = parts_of(data, claim)
    miss = next((p for p in rows if not meets(data, p, level)), None)
    need = BAR_WORDS.get(level, level)
    why = below_reason(data, miss, level) if miss else ""
    text = f"Bar: {need} · met" if not miss else f"Bar: {need} · below the bar: {why}"
    return {"surface": surf, "surfaces": found, "mixed": surf == "unsure",
            "risky": kind == "risky", "level": level, "need": need, "met": not miss, "why": why,
            "part": miss["id"] if miss and len(rows) > 1 else None, "text": text}


# ---- Plain names -------------------------------------------------------------------------------

TOOLS = re.compile(r"(?i)\b(basedpyright|pyright|mypy|pytest|unittest|ruff|eslint|oxlint|tsc|git grep|grep|lake|tlc|apalache|"
                   r"uv run|npm|cargo|playwright|cc-check)\b")
PATHY = re.compile(r"[\w-]+/[\w./-]+|\b[\w-]+\.(?:py|ts|tsx|js|mjs|rs|go|lean|tla|json|toml|md|sh|ya?ml)\b|::|\w\(")
CODEY = re.compile(r"`|\b[a-z][a-z0-9]*_[a-z0-9_]+\b|\b[A-Z][a-z0-9]+[A-Z]\w*\b|\b[a-z]+[A-Z]\w*\b")
_SMALL = {"the", "a", "an"}


def _words(text: str) -> list[str]:
    text = re.sub(r"`([^`]*)`", r"\1", text or "").lower()
    return [w for w in re.findall(r"[a-z0-9']+", text)]


def _core(words: list[str]) -> list[str]:
    while words and words[0] in _SMALL:
        words = words[1:]
    return words


def name_problem(name: str | None, sources: list[str], mechanical: list[str] = ()) -> str | None:
    """Why a plain name is not acceptable, or None. A name is 2 to 6 words, as a reviewer says it:
    not a cut of the plain text, no path, no tool name, no code name."""
    if not name or not name.strip():
        return "it has no name"
    words = name.split()
    if not 2 <= len(words) <= 6:
        return f"it has {len(words)} words; write 2 to 6"
    if PATHY.search(name):
        return "it holds a path or a file name"
    if TOOLS.search(name):
        return f"it names a tool ({TOOLS.search(name).group(0)})"
    if CODEY.search(name):
        return "it holds a code name"
    mine = _core(_words(name))
    for text in sources:
        theirs = _core(_words(text))
        # A cut of a sentence runs into its verb; a short noun phrase that starts the claim is fine.
        if len(mine) >= 4 and theirs[:len(mine)] == mine and len(theirs) > len(mine):
            return "it is the first words of the plain text, cut off"
    if any(name.strip().lower() == m.strip().lower() for m in mechanical if m):
        return "it is the name that the old mechanical rule makes"
    return None


def name_problems(data: dict) -> list[tuple[str, str, str]]:
    """(kind, id, why) for each promise, claim and check whose name is not acceptable."""
    import names
    out = []
    for p in data.get("promises", []):
        why = name_problem(p.get("name"), [p.get("sentence", "")])
        if why:
            out.append(("promise", p["id"], why))
    claims = {c["id"]: c for c in data["claims"]}
    for c in data["claims"]:
        what = (c.get("plain") or {}).get("what") or ""
        why = name_problem(c.get("name"), [what, c.get("text", "")], [names.short(what or c.get("text", ""))])
        if why:
            out.append(("claim", c["id"], why))
    for v in data["verifiers"]:
        if not is_tool(v):
            continue
        why = name_problem(v.get("name"), [v.get("description", "")], [names.verifier_name(v, claims)])
        if why:
            out.append(("check", v["id"], why))
    return out


# ---- The grouping lint -------------------------------------------------------------------------

RISK = [("safety", re.compile(r"(?i)\b(safety|harm|secrets?|auth|authentication|privacy|sandbox)\b")),
        ("money", re.compile(r"(?i)(\bcost|\bprice|\busd\b|\$\d|billing|meter|budget|per document)")),
        ("anti-gaming", re.compile(r"(?i)\b(gaming|game|judge|editable|confirm\w*|accept rule|anti-gaming)\b")),
        ("clinical", re.compile(r"(?i)\b(clinician review|clinical|patients?|care plan)\b")),
        ("production", re.compile(r"(?i)\b(production|prod|cr_service)\b"))]


def risk_tags(claim: dict) -> tuple[str, ...]:
    """The risky surfaces that a claim names in its plain words. Code names do not count."""
    text = " ".join([claim.get("text", ""), (claim.get("plain") or {}).get("what", ""), claim.get("layer", "")])
    text = CODEY.sub(" ", re.sub(r"`[^`]*`", " ", text))
    return tuple(tag for tag, rx in RISK if rx.search(text))


def action_kind(data: dict, claim: dict) -> str:
    v, _ = weakest_check(data, claim)
    return check_result(data, v) if v else "none"


def promise_of(data: dict) -> dict[str, str]:
    return {cid: p["id"] for p in data.get("promises", []) for cid in p["claims"]}


def group_lint(data: dict) -> list[str]:
    """Merge suggestions that match the merge rule, then a warning for each budget that the map leaves."""
    import names
    owner = promise_of(data)
    groups: dict[tuple, list[dict]] = {}
    for c in data["claims"]:
        kinds = tuple(sorted({v["kind"] for v in checks_of(data, c)}))
        key = (owner.get(c["id"]), kinds, action_kind(data, c), risk_tags(c))
        groups.setdefault(key, []).append(c)
    out = []
    candidates: dict[str, list[str]] = {}
    for (pid, kinds, action, risk), cs in groups.items():
        if len(cs) < 2 or kinds == ("none",):
            continue
        label = next((p.get("name") or p.get("label") for p in data["promises"] if p["id"] == pid), pid)
        ids = [c["id"] for c in cs]
        candidates.setdefault(pid, []).append(", ".join(ids))
        out.append(f"merge: {names.listing([names.of(data, i) for i in ids], top=6)} have the same promise ('{label}'), the same kind of check "
                   f"({', '.join(kinds)}) and the same reviewer action. Make them one claim with {sum(len(checks_of(data, c)) for c in cs)} checks, "
                   f"unless a reviewer could accept one and reject another." + names.ref(ids, n=12))
    for v in data["verifiers"]:
        own = claims_of(data, v)
        if v["kind"] in ("tla", "lean") and len(own) > 1 and not v.get("property"):
            out.append(f"split: {names.of(data, v['id'])} backs {len(own)} claims. Make one check for each property (a TLA+ invariant or "
                       f"property, or a Lean theorem group), each with its own controls, under the claim that states it." + names.ref([v["id"]]))
    for c in data["claims"]:
        if surface(data, c) == "unsure":
            found = [x for x in surfaces(data, c) if x != "other"]
            out.append(f"surface: '{names.of(data, c['id'])}' is unsure: its signals say {' and '.join(found)}. Ask the user once, and set its "
                       f"surface (frontend, backend, llm or other); it decides the evidence bar." + names.ref([c["id"]]))
    lo, hi = BUDGET["promises"]
    if not lo <= len(data.get("promises", [])) <= hi:
        out.append(f"budget: {len(data.get('promises', []))} promises; write {lo} to {hi}.")
    lo, hi = BUDGET["per_promise"]
    for p in data.get("promises", []):
        n = len(p["claims"])
        if n > hi:
            cand = candidates.get(p["id"])
            out.append(f"budget: the promise '{p.get('name') or p['label']}' has {n} claims; about {lo} to {hi} is the budget. "
                       + (f"Merge candidates: {'; '.join(cand)}." if cand else "Merge the claims that a reviewer accepts or rejects together."))
    lo, hi = BUDGET["claims"]
    n = len(data["claims"])
    if n > hi:
        cand = [x for xs in candidates.values() for x in xs]
        out.append(f"budget: {n} claims; about {lo} to {hi} is the budget. " + (f"Merge candidates: {'; '.join(cand)}." if cand else
                   "Merge the claims that a reviewer accepts or rejects together."))
    elif n < lo:
        out.append(f"budget: {n} claims; about {lo} to {hi} is the budget. A small PR can have fewer. Split a claim only when a reviewer could accept one part and reject another.")
    return out


def main(argv: list[str]) -> int:
    """python3 scripts/onto.py upgrade MAP   write MAP in shape 2
       python3 scripts/onto.py lint MAP      the merge suggestions, the budget, the surfaces and the plain names
       python3 scripts/onto.py bars MAP      the surface, the risk and the evidence bar of each claim"""
    if len(argv) == 2 and argv[0] == "bars":
        data = tm.load(argv[1])
        import names
        for c in data["claims"]:
            b = bar(data, c)
            print(f"{c['id']}\t{b['surface']}{' (mixed)' if b['mixed'] else ''}\t{'risky' if b['risky'] else 'normal'}\t{b['text']}\t{names.of(data, c['id'])}")
        return 0
    if len(argv) != 2 or argv[0] not in ("upgrade", "lint"):
        tm.fail(main.__doc__)
    data = tm.load(argv[1])
    if argv[0] == "upgrade":
        n = upgrade(data)
        tm.save(data, argv[1])
        print(f"onto: {n} changes; {argv[1]} is in shape {SHAPE}")
        return 0
    import names
    lines = group_lint(data) + [f"name: the {k} '{names.of(data, i)}' is not plain: {why}.{names.ref([i])}" for k, i, why in name_problems(data)]
    print("\n".join(lines) if lines else "onto: no merge suggestion, the map is in its budget, and each name is plain")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
