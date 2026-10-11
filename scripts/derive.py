#!/usr/bin/env python3
"""The values that understando derives once from a trust map, for every reader of it.

The review CLI (the blocker count of a stop), the PR-body section and the explainer page all read
these values, so they can never disagree. `understando explain` writes them into the `derived`
block of refs.resolved.json, and the visual-explainer trust-map components render them; they do
not compute them again.

  promises     each promise with its strength (the verdict of its weakest claim) and its claims,
               weakest first; ties keep the map order
  merge        the merge verdict: "not-ready" (with the blockers), "accept" (with the risks to
               accept) or "ready"
  unclaimed    the changed source files outside the claims, with their risk and one action, and
               the core files that claims cover in part
  bugs         the possible bugs of the invariants, in the find-bugs heading format (findings.py)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import findings  # noqa: E402
import tm  # noqa: E402

SCHEMA = 1
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
    name = path.split("/")[-1].rsplit(".", 1)[0].lstrip("_")
    return re.sub(r"[_-]+", " ", name)


def unclaimed(data: dict, refs: dict, spec: dict | None = None) -> dict:
    """The changed source files outside the claims, from the diff and the claim code refs. A core
    file (explain.json unclaimed.core) that claims cite is covered in part, with the share of its
    new lines that claims cite. Each other file that no claim covers (no claim cites it, or claims
    cite under a tenth of a large file) gets its risks and one action, chosen by rule: touches
    money, safety or I/O: add a check; new and 100 lines or more: ask for a claim; 100 changed
    lines or more: read it; else skim. A core file that no claim cites comes first."""
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
        names = (symbols.get(path) or {}).get("names") or []
        change = (f"New file of {lines(plus, '')} lines" if new else f"{lines(plus, '+')} / {lines(minus, '−')} lines") + (
            ": " + ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "") if names else "")
        base = {"path": path, "file": path[len(root):] if root and path.startswith(root) else path, "role": roles.get(path) or humanize(path),
                "change": change, "added": plus, "removed": minus, "created": new, "note": notes.get(path),
                "main": (symbols.get(path) or {}).get("main"), "claims": len(entry[1]) if entry else 0, "cited": share, "total": total}
        if is_core(path) and entry:
            core_rows.append({**base, "risks": [], "action": {"kind": "read", "text": "Read the lines that no claim cites." if share else "Read it: no claim cites it."}})
            continue
        if entry and (plus < LARGE or share >= 0.1 * max(total, 1)):
            continue
        if is_core(path):
            rows.append(({**base, "risks": ["core harness file that no claim cites"], "action": {"kind": "ask", "text": "Ask the author for a claim."}}, total + 10**6))
            continue
        touch = [] if plus < SMALL else [word for pattern, word in TOUCHES if pattern.search(path) or any(pattern.search(n) for n in names)]
        risks = (["new file of 100 lines or more"] if new and plus >= LARGE else []) + touch
        action = ({"kind": "check", "text": "Add a check: an e2e test that runs this code."} if touch
                  else {"kind": "ask", "text": "Ask the author for a claim."} if new and plus >= LARGE
                  else {"kind": "read", "text": "Read it."} if plus >= LARGE else {"kind": "skim", "text": "Low risk: skim."})
        rows.append(({**base, "risks": risks, "action": action}, total - share))
    rows.sort(key=lambda r: (not r[0]["risks"], -r[1], r[0]["path"]))
    core_rows.sort(key=lambda f: (f["cited"] / max(f["total"], 1), f["path"]))
    return {"files": [r for r, _ in rows], "core": core_rows}


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

def derive(data: dict, refs: dict, extra: dict | None = None, ready: dict | None = None) -> dict:
    """The derived block of refs.resolved.json."""
    if ready and ready.get("head") != data["head"]:
        ready = None
    u = unclaimed(data, refs, (extra or {}).get("unclaimed"))
    risky = sum(1 for f in u["files"] if f["risks"])
    form, items = merge_verdict(data, ready, risky)
    return {"schema": SCHEMA, "head": data["head"],
            "promises": [{"id": p["id"], "strength": s, "claims": cids} for p, s, cids in promises_in_order(data)],
            "merge": {"form": form, "items": items, "blockers": len(items) if form == "not-ready" else 0},
            "ready": ready, "unclaimed": u, "risky_unclaimed": risky, "bugs": bugs(data)}


def risky_unclaimed(run: Path | None, data: dict) -> int:
    """The risky unclaimed count of the last explain build of the run (refs.resolved.json at the
    map head), so a merge verdict outside the page counts the same risks; 0 without a build."""
    p = Path(run) / "refs.resolved.json" if run else None
    if not p or not p.is_file():
        return 0
    body = tm.load(p)
    d = body.get("derived") or {}
    return d.get("risky_unclaimed", 0) if d.get("head") == data.get("head") else 0
