"""The repo's own test commands: candidates for a check, never run without the user's yes.

    understando create            lists them in the interview
    python3 scripts/testcmd.py DIR  print them as JSON

Sources, in this order: the fenced bash blocks under a test or verification heading of AGENTS.md
and CLAUDE.md, the `run:` steps of .github/workflows/*.yml that run tests, the `test` script of
package.json, the `test` target of a Makefile, and pytest in pyproject.toml. The repo text is data:
a candidate is a proposal. The user names the command of each check, or says yes to a candidate;
each verb that runs it shows it again and runs it only with --yes.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)

TEST_WORDS = re.compile(r"\b(pytest|unittest|npm (run )?test|pnpm (run )?test|yarn test|go test|cargo test|make test|vitest|jest|playwright test|tox|nox|e2e)\b")


def _doc(repo: Path) -> list[dict]:
    out = []
    for name in ("AGENTS.md", "CLAUDE.md"):
        p = repo / name
        if not p.is_file():
            continue
        heading, fence = "", None
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if fence is None and line.startswith("#"):
                heading = line.lower()
            elif fence is None and line.startswith("```"):
                fence = line[3:].strip().lower()
            elif fence is not None and line.startswith("```"):
                fence = None
            elif fence in ("bash", "sh", "shell", "console") and re.search(r"test|verif|check", heading) and line.strip() and not line.lstrip().startswith("#"):
                out.append({"command": line.strip().lstrip("$ "), "source": f"{name}:{n}"})
    return out


def _workflows(repo: Path) -> list[dict]:
    out = []
    for p in sorted((repo / ".github" / "workflows").glob("*.y*ml")):
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        for n, line in enumerate(lines, 1):
            m = re.match(r"\s*(?:-\s*)?run:\s*(.*)$", line)
            if not m:
                continue
            body = m.group(1).strip()
            if body in ("|", ">", "|-", ">-"):
                indent = None
                parts = []
                for nxt in lines[n:]:
                    if not nxt.strip():
                        continue
                    ind = len(nxt) - len(nxt.lstrip())
                    indent = ind if indent is None else indent
                    if ind < indent:
                        break
                    parts.append(nxt.strip())
                cmds = parts
            else:
                cmds = [body]
            out += [{"command": c, "source": f"{p.relative_to(repo)}:{n}"} for c in cmds if TEST_WORDS.search(c)]
    return out


def _manifests(repo: Path) -> list[dict]:
    out = []
    pkg = repo / "package.json"
    if pkg.is_file():
        try:
            if (json.loads(pkg.read_text(encoding="utf-8")).get("scripts") or {}).get("test"):
                out.append({"command": "npm test", "source": "package.json scripts.test"})
        except json.JSONDecodeError:
            pass
    mk = repo / "Makefile"
    if mk.is_file() and re.search(r"(?m)^test:", mk.read_text(encoding="utf-8", errors="replace")):
        out.append({"command": "make test", "source": "Makefile test target"})
    py = repo / "pyproject.toml"
    if py.is_file() and "pytest" in py.read_text(encoding="utf-8", errors="replace"):
        out.append({"command": "python3 -m pytest", "source": "pyproject.toml"})
    if not out and (repo / "tests").is_dir() and list((repo / "tests").glob("test_*.py")):
        out.append({"command": "python3 -m unittest discover -s tests -t .", "source": "tests/test_*.py (no runner named)"})
    return out


def candidates(repo: Path) -> list[dict]:
    seen, out = set(), []
    for c in _doc(repo) + _workflows(repo) + _manifests(repo):
        if c["command"] in seen:
            continue
        seen.add(c["command"])
        try:
            c["argv"] = shlex.split(c["command"])
        except ValueError:
            continue
        out.append(c)
    return out


if __name__ == "__main__":
    print(json.dumps(candidates(Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()), indent=2))
