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


def weakest_check(data: dict, claim: dict) -> tuple[dict | None, str | None]:
    """The weakest check of a claim: the weakest strength, then the worst result. Ties keep the order."""
    best = None
    alone = {**claim, "stated": True, "parts": None}
    for v in checks_of(data, claim):
        # The weakest strength first; then the check that is weak by itself, not only by the intent
        # rule; then the worst result.
        key = (-VERDICTS.index(check_strength(data, v, claim)), -VERDICTS.index(check_strength(data, v, alone)),
               RESULTS.index(check_result(data, v)))
        if best is None or key < best[0]:
            best = (key, v)
    return (best[1], check_strength(data, best[1], claim)) if best else (None, None)


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
       python3 scripts/onto.py lint MAP      the merge suggestions, the budget and the plain names"""
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
