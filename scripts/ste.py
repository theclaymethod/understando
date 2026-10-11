"""The asd-ste100 gate: run the STE lint of the installed skill on text that a reviewer reads.

asd-ste100 is required. understando has no adapted copy of it, and `understando setup` installs it.
The agent applies the skill while it writes (SKILL.md, "Rules for every verb"). This module is the
mechanical half: it runs `python3 -I <asd-ste100>/scripts/ste-lint.py --json` on the text and
returns each hard violation (a semicolon, a long sentence, a rotating synonym, a marketing word,
a soft phrasal verb, a frozen action noun). A hard violation fails the prompt render, the map
check of claims and names, the PR section and the README of publish.

    python3 scripts/ste.py FILE...      lint each file; exit 1 on a hard violation or a missing lint
"""

from __future__ import annotations

import functools
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)

SKILL = "asd-ste100"
MISSING = ("the STE lint (asd-ste100) is not installed. It is required for the text that a reviewer reads. "
           "Run `understando setup` to install it.")


class SteMissing(RuntimeError):
    pass


def lint_path() -> Path | None:
    import routes
    found = routes.find_skill(SKILL)
    p = found / "scripts" / "ste-lint.py" if found else None
    return p if p and p.is_file() else None


@functools.lru_cache(maxsize=512)
def _hard(text: str, lint: str) -> tuple[str, ...]:
    out = subprocess.run([sys.executable, "-I", lint, "--json"], input=text, capture_output=True, text=True, timeout=120)
    try:
        report = json.loads(out.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"the STE lint gave no report: {(out.stderr or out.stdout).strip()[:200]}") from e
    lines = text.splitlines()
    found = []
    for f in report["violations"]:
        if f["level"] == "advisory-free":
            row = lines[f["line"] - 1].strip() if 0 < f["line"] <= len(lines) else ""
            found.append(f"{f['rule']} [{f['match']}] in: {row[:140]}")
    return tuple(found)


def hard_violations(text: str) -> list[str]:
    """The hard STE violations of a text. Raises SteMissing when asd-ste100 is not installed."""
    lint = lint_path()
    if not lint:
        raise SteMissing(MISSING)
    return list(_hard(text, str(lint)))


def prose(text: str) -> str:
    """The text without its "(ref: ...)" parts: IDs, SHAs and paths are not prose."""
    return re.sub(r"\s*\(ref: [^)]*\)", "", text or "")


def require(texts: list[str], what: str) -> None:
    """Raise ValueError when the STE lint finds a hard violation in the texts. One text for each line."""
    body = "\n".join(prose(t) for t in texts if t)
    bad = hard_violations(body)
    if bad:
        raise ValueError(f"{what}: the text is not strict STE (asd-ste100): " + "; ".join(bad))


def map_texts(data: dict) -> list[str]:
    """The prose that a map holds: claim statements, plain text, names, promises and glossary."""
    out: list[str] = []

    def add(x):
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
        elif isinstance(x, dict):
            for v in x.values():
                add(v)
        elif isinstance(x, list):
            for v in x:
                add(v)

    for c in data.get("claims", []):
        for k in ("text", "name"):
            add(c.get(k))
        for k in ("what", "proof", "warning"):
            add((c.get("plain") or {}).get(k))
        add([p.get("text") if isinstance(p, dict) else p for p in c.get("parts", [])])
    for p in data.get("promises", []):
        for k in ("label", "sentence", "reviewer_action", "name"):
            add(p.get(k))
    for v in data.get("verifiers", []):
        add(v.get("name"))
        add(v.get("description"))
    for i in data.get("invariants", []):
        add(i.get("text"))
    add([g.get("meaning") for g in data.get("glossary", [])])
    for k in data.get("controls", []):
        add(k.get("name"))
        add(k.get("description"))
    add(data.get("verdict_intros"))
    return out


def map_problems(data: dict) -> list[str]:
    """One finding for each map text that has a hard STE violation (claims, plain text, names, promises)."""
    problems = []
    for t in map_texts(data):
        for b in hard_violations(prose(t)):
            problems.append(f"not strict STE: {b}")
    return problems


def main(argv: list[str]) -> int:
    code = 0
    for a in argv:
        try:
            bad = hard_violations(Path(a).read_text(encoding="utf-8"))
        except SteMissing as e:
            print(e, file=sys.stderr)
            return 1
        for b in bad:
            print(f"{a}: {b}")
        code = code or int(bool(bad))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
