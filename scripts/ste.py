"""The asd-ste100 gate: run the STE lint of the installed skill on the written claim text.

asd-ste100 is required. understando has no adapted copy of it, and `understando setup` installs it.
The agent applies the skill while it writes (SKILL.md, "Rules for every verb"). This module is the
mechanical half: it runs `python3 -I <asd-ste100>/scripts/ste-lint.py --json` on the text and
returns each hard violation (a semicolon, a long sentence, a rotating synonym, a marketing word,
a soft phrasal verb, a frozen action noun). A hard violation fails the written claim and
invariant text (discover answer, build claim).

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
MISSING = ("the STE lint (asd-ste100) is not installed. It is required for the written claim text. "
           "Run `understando setup` to install it.")


class SteMissing(RuntimeError):
    pass


@functools.lru_cache(maxsize=None)
def lint_path() -> Path | None:
    import toolprobe
    found = toolprobe.find_skill(SKILL)
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


def require_or_fail(texts: list[str], what: str, hint: str = "") -> None:
    """require(), for a verb: exit 1 when the lint is missing, exit 2 on a hard violation (with the hint)."""
    import store
    try:
        require(texts, what)
    except SteMissing as exc:
        store.fail(str(exc), 1)
    except ValueError as exc:
        store.fail(f"{exc} {hint}" if hint else str(exc), 2)


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
