"""The one-question prompt that review, menu, ci and close end with.

A prompt is {situation: [lines], next: {...} | None, question, options: [{id, label, does, run?, recommended?}]}.
The CLI writes the wording, so each agent only relays it (references/working-rules.md, "Asking the user").

Rules that check() enforces: at most 5 situation lines, 2 to 4 options, option 1 is the recommended
default, and the last option is "Something else".
"""

from __future__ import annotations

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


def make(situation: list[str], question: str, options: list[dict], nxt: dict | None = None,
         else_does: str = "Tell me what to do instead. Nothing runs until you say.") -> dict:
    """Number the options, mark option 1 recommended, and add "Something else" as the last option."""
    opts = [o for o in options if o][:MAX_OPTIONS - 1]
    for o in opts:
        o.pop("recommended", None)
    if opts:
        opts[0]["recommended"] = True
    opts.append({"label": ELSE, "does": else_does})
    for i, o in enumerate(opts, 1):
        o["id"] = i
    p = {"situation": [s for s in situation if s][:MAX_SITUATION], "next": nxt, "question": question, "options": opts}
    check(p)
    return p


def check(p: dict) -> None:
    opts = p["options"]
    assert len(p["situation"]) <= MAX_SITUATION, p["situation"]
    assert 2 <= len(opts) <= MAX_OPTIONS, opts
    assert opts[0].get("recommended") and opts[-1]["label"] == ELSE, opts


def next_line(n: dict) -> str:
    parts = [n["does"]]
    for key, name in (("scope", "Scope"), ("cost", "Cost"), ("time", "Time"), ("writes", "Writes")):
        if n.get(key):
            parts.append(f"{name}: {n[key]}")
    return "Next: " + ". ".join(p.rstrip(".") for p in parts) + "."


def render(p: dict) -> str:
    lines = list(p["situation"])
    if p.get("next"):
        lines.append(next_line(p["next"]))
    lines += ["", p["question"]]
    for o in p["options"]:
        mark = " (recommended)" if o.get("recommended") else ""
        lines.append(f"  {o['id']}. {o['label']}{mark}: {o['does']}")
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
