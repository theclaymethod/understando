"""The one-question prompt that review, menu, ci and close end with.

A prompt is {situation: [lines], next: {...} | None, question, options: [{id, label, does, run?, recommended?}]}.
The CLI writes the wording, so each agent only relays it (references/working-rules.md, "Asking the user").

Rules that check() enforces: at most 5 situation lines, 2 to 4 options, option 1 is the recommended
default, and the last option is "Something else". The words that a user reads (the situation, the
question, each label and `does`, and the Next line) use plain names. A bare internal ID (C15, V19, K03,
L3, F489-2), a hex SHA or a `path:line` fails the check. IDs, SHAs and paths go in a trailing
"(ref: ...)" part, in `details` (shown only with --verbose), or in the JSON fields (`run`, `refs`).
"""

from __future__ import annotations

import re

MAX_SITUATION = 5
MAX_OPTIONS = 4
ELSE = "Something else"


def option(label: str, does: str, run: str | None = None, recommended: bool = False) -> dict:
    o = {"label": label, "does": does}
    if run:
        o["run"] = run
    if recommended:
        o["recommended"] = True
    return o


REF = re.compile(r"\(ref: [^)]*\)")
INTERNAL_ID = re.compile(r"(?<![\w-])(?:[ACGVKIL]\d+(?:-\w+)?|F\d+(?:-\w+)?|CI\d+)(?![\w-])")
HEX_SHA = re.compile(r"(?<![\w-])(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}(?![\w-])")
PATH_LINE = re.compile(r"[\w./-]+\.[A-Za-z]{1,5}:\d+(?:-\d+)?(?:,\s*\d+(?:-\d+)?)*")


def plain_problems(text: str) -> list[str]:
    """The internal names that a user-facing text shows outside a "(ref: ...)" part."""
    bare = REF.sub("", text or "")
    out = []
    for name, rx in (("an internal ID", INTERNAL_ID), ("a SHA", HEX_SHA), ("a path:line", PATH_LINE)):
        m = rx.search(bare)
        if m:
            out.append(f"{name} ({m.group(0)!r}) in: {text}")
    return out


def user_texts(p: dict) -> list[str]:
    texts = list(p["situation"]) + [p["question"]]
    n = p.get("next") or {}
    texts += [n.get(k, "") for k in ("does", "scope", "cost", "time", "writes")]
    for o in p["options"]:
        texts += [o["label"], o["does"]]
    return [t for t in texts if t]


def make(situation: list[str], question: str, options: list[dict], nxt: dict | None = None,
         else_does: str = "Tell me what to do instead. Nothing runs until you say.", details: list[str] | None = None) -> dict:
    """Number the options, mark option 1 recommended, and add "Something else" as the last option."""
    opts = [o for o in options if o][:MAX_OPTIONS - 1]
    for o in opts:
        o.pop("recommended", None)
    if opts:
        opts[0]["recommended"] = True
    opts.append({"label": ELSE, "does": else_does})
    for i, o in enumerate(opts, 1):
        o["id"] = i
    p = {"situation": [s for s in situation if s][:MAX_SITUATION], "next": nxt, "question": question, "options": opts,
         "details": [d for d in (details or []) if d]}
    check(p)
    return p


def check(p: dict) -> None:
    opts = p["options"]
    assert len(p["situation"]) <= MAX_SITUATION, p["situation"]
    assert 2 <= len(opts) <= MAX_OPTIONS, opts
    assert opts[0].get("recommended") and opts[-1]["label"] == ELSE, opts
    bad = [x for t in user_texts(p) for x in plain_problems(t)]
    if bad:
        raise ValueError("prompt: the user-facing text must use plain names: " + "; ".join(bad))


def next_line(n: dict) -> str:
    """Two lines: "Next: <one short sentence>." and "Scope: ... Cost: ... Time: ... Writes: ..."."""
    parts = []
    for key, name in (("scope", "Scope"), ("cost", "Cost"), ("time", "Time"), ("writes", "Writes")):
        if n.get(key):
            parts.append(f"{name}: {n[key].rstrip('.')}")
    return "Next: " + n["does"].rstrip(".") + "." + ("\n" + ". ".join(parts) + "." if parts else "")


def render(p: dict, verbose: bool = False) -> str:
    lines = list(p["situation"])
    if p.get("next"):
        lines.append(next_line(p["next"]))
    lines += ["", p["question"]]
    for o in p["options"]:
        mark = " (recommended)" if o.get("recommended") else ""
        lines.append(f"  {o['id']}. {o['label']}{mark}: {o['does']}")
    if verbose and p.get("details"):
        lines += ["", "Details:"] + [f"  {d}" for d in p["details"]]
    return "\n".join(lines)


def human_seconds(s: float | None) -> str | None:
    if s is None:
        return None
    s = int(round(s))
    if s < 60:
        return f"about {max(s, 1)} s"
    if s < 3600:
        return f"about {round(s / 60)} min"
    return f"about {s / 3600:.1f} h"


def n_of(n: int, word: str, plural: str | None = None) -> str:
    return f"{n} {word if n == 1 else (plural or word + 's')}"
