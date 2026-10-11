"""Plain names for chat: each promise, claim and check has a short `name` that a reviewer can read.

A reviewer does not know what C15 or V19 is. Every prompt, situation line, option and stop report
uses these names; the IDs go only in a trailing "(ref: ...)" part, in --verbose output or in JSON.

The agent writes each name: 2 to 6 words, in STE, as a reviewer says it ("the idle stop", "the
project-wide type check", "the import boundary", "the accept rule"). map refuses a promise, a claim
or a check with no name, and doctor flags a name that is a cut of `plain.what`, or that holds a
path or a tool name (onto.name_problems). The mechanical rules below are only a display fallback
for an old map, and the rule that names an invariant:
  - a claim or an invariant: from `plain.what` (else `text`), 3 to 7 words. "If X, Y." gives Y.
  - a verifier: what it checks. A test selector names the test; else its kind and its first claim.
"""

from __future__ import annotations

import re
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)

MAX_WORDS = 7
CUT_WORDS = {"that", "which", "because", "when", "unless", "so", "while", "and", "but", "or", "with"}
KIND_WORD = {"e2e": "end-to-end test", "integration": "test", "unit": "unit test", "golden": "golden test", "parity": "parity test",
             "eval": "eval", "measurement": "measurement", "property": "property test", "fuzz": "fuzz test",
             "type-pin": "type check", "contract": "contract", "contract-format": "contract format check",
             "boundary": "boundary check", "static": "static check", "tla": "model check", "lean": "proof", "model": "model review"}


def _clean(text: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", text or "")
    text = re.sub(r"\([^)]*\)", "", text)
    return re.sub(r"\s+", " ", text).strip()


TAIL_WORDS = {"a", "an", "the", "to", "of", "its", "in", "by", "for", "from", "with", "one", "can", "not", "does", "be", "is",
              "are", "on", "at", "or", "and", "but", "that", "only", "than", "into", "it", "their", "this"}


def trim(words: list[str]) -> list[str]:
    """Drop the small words at the end of a cut phrase, so it does not end on "the" or "to"."""
    while len(words) > 3 and words[-1].lower().strip(",.") in TAIL_WORDS:
        words = words[:-1]
    return words


def short(text: str, max_words: int = MAX_WORDS) -> str:
    """3 to max_words words from a plain sentence: its first sentence, its main clause, its first part."""
    s = _clean(text)
    s = re.split(r"(?<=[.!?])\s", s, maxsplit=1)[0].rstrip(".!?")
    if re.match(r"(?i)(?:if|when|after|once)\b", s) and "," in s:
        main = re.sub(r"(?i)^then\s+", "", s.rsplit(",", 1)[1].strip())
        if len(main.split()) >= 3:
            s = main
    s = re.split(r"[;:,]", s, maxsplit=1)[0] if len(re.split(r"[;:,]", s, maxsplit=1)[0].split()) >= 3 else s
    words = s.split()
    for i, w in enumerate(words):
        if i >= 3 and w.lower() in CUT_WORDS:
            words = words[:i]
            break
    words = trim(words[:max_words])
    out = " ".join(words).strip(" ,;:")
    return out[:1].lower() + out[1:] if out.startswith(("The ", "A ", "An ")) else out


def test_name(v: dict) -> str | None:
    """The test function or class that a command selects, as words."""
    for a in reversed((v.get("command") or {}).get("argv") or []):
        m = re.search(r"(?:::|\.)(test_\w+|Test\w+|\w+Test)$", a)
        if m:
            raw = m.group(1)
            if raw.startswith("test_"):
                return raw[5:].replace("_", " ")
            return re.sub(r"(?<!^)(?=[A-Z])", " ", raw).lower().replace(" test", "").strip()
    return None


def verifier_name(v: dict, claims: dict[str, dict]) -> str:
    word = KIND_WORD.get(v.get("kind", ""), "check")
    t = test_name(v)
    if t and len(t.split()) >= 3:
        return f"the {word} that {' '.join(trim(t.split()[:MAX_WORDS + 2]))}"
    first = claims.get((v.get("claims") or [""])[0])
    about = (first or {}).get("name") or short((first or {}).get("text", ""))
    return f"the {word} of {about}" if about else f"the {word}"


def fill(data: dict) -> int:
    """Add a missing `name` to each invariant. Returns how many it added. A promise, a claim and a
    check get no mechanical name: the agent writes it (missing)."""
    n = 0
    for i in data.get("invariants", []):
        if not i.get("name"):
            i["name"] = short(i.get("text", ""))
            n += 1
    return n


def missing(data: dict) -> list[str]:
    """The promises, claims and checks that have no name. map refuses them."""
    out = [f"promise {p['id']}" for p in data.get("promises", []) if not p.get("name")]
    out += [f"claim {c['id']}" for c in data.get("claims", []) if not c.get("name")]
    out += [f"check {v['id']}" for v in data.get("verifiers", []) if not v.get("name")]
    return out


def of(data: dict, item_id: str) -> str:
    """The plain name of a claim, verifier, invariant or promise ID; the ID itself goes in a ref."""
    for key in ("claims", "verifiers", "invariants"):
        for x in data.get(key, []):
            if x["id"] == item_id:
                return x.get("name") or (short(x.get("text", "")) if key != "verifiers" else verifier_name(x, {c["id"]: c for c in data["claims"]}))
    for p in data.get("promises", []):
        if p["id"] == item_id:
            return p.get("name") or p.get("label") or item_id
    return item_id


def checks_of(data: dict, claim: dict | str) -> list[dict]:
    """The checks of a claim (promise -> claim -> check), in either shape (onto.checks_of)."""
    import onto
    return onto.checks_of(data, claim)


def listing(names: list[str], top: int = 3) -> str:
    """Name the top 3, then a count: "a, b, c and 4 more"."""
    names = [n for n in names if n]
    if len(names) <= top:
        return ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + (names[-1] if names else "")
    return ", ".join(names[:top]) + f" and {len(names) - top} more"


LEAD = r"(?:(?:\b(?:on|at|in|by)\s+)?(?:the\s+)?(?:control|verifier|claim|invariant|record|commit|possible bug)s?\s+)?"


def scrub(text: str) -> str:
    """Move the internal IDs, SHAs and path:line parts of a text into one trailing "(ref: ...)" part,
    with the word that names them ("control K01", "at 3758b090"), so the text passes the plain-name
    rule of scripts/prompt.py. Prefer a plain sentence; use this for text that a person wrote."""
    import prompt
    found: list[str] = []

    def take(m: re.Match) -> str:
        found.append(m.group("x"))
        return ""
    body = prompt.REF.sub(lambda m: found.append(m.group(0)[6:-1]) or "", text or "")
    for rx in (prompt.PATH_LINE, prompt.HEX_SHA, prompt.INTERNAL_ID):
        body = re.sub(LEAD + "(?P<x>" + rx.pattern + ")", take, body)
    body = re.sub(r"\(\s*(?:(?:,|;|and)\s*)*\)", "", body)
    body = re.sub(r"\s+([,.;:])", r"\1", re.sub(r"\s{2,}", " ", body)).strip()
    body = re.sub(r"(?:,\s*)+(and\b)?\s*(?=[.;:]|$)", "", body)
    return body + (ref(list(dict.fromkeys(found))) if found else "")


def plainify(text: str, data: dict) -> str:
    """Replace each internal ID of a text with its plain name in quotes, and move the IDs to a ref."""
    import prompt
    ids: list[str] = []

    def sub(m: re.Match) -> str:
        ids.append(m.group(0))
        if any(k["id"] == m.group(0) for k in data.get("controls", [])):
            return "its planted bug"
        n = of(data, m.group(0))
        return f"'{n}'" if n != m.group(0) else "a check"
    body = prompt.INTERNAL_ID.sub(sub, prompt.REF.sub("", text or ""))
    body = re.sub(r"\bcontrols? its planted bug", "its planted bug", body)
    return scrub(body).split(" (ref:")[0] + ref(list(dict.fromkeys(ids)))


def ref(ids: list[str], n: int = 6) -> str:
    ids = [i for i in ids if i]
    return f" (ref: {', '.join(ids[:n])}{' ...' if len(ids) > n else ''})" if ids else ""
