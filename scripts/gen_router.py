#!/usr/bin/env python3
"""Write the verb table of SKILL.md from commands.json, between the two router markers.

    python3 scripts/gen_router.py            rewrite SKILL.md
    python3 scripts/gen_router.py --check    exit 1 when SKILL.md and commands.json differ
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START, END = "<!-- verbs:start (scripts/gen_router.py writes this table) -->", "<!-- verbs:end -->"
WHO = {"model": "you or the user", "user": "the user only", "hook": "a prompt hook only"}


def table() -> str:
    cmds = json.loads((ROOT / "commands.json").read_text(encoding="utf-8"))
    rows = ["| Verb | Category | Job | Who starts it | Read |", "|---|---|---|---|---|"]
    for v in cmds["verbs"]:
        if v["invoke"] == "hook":
            continue
        who = WHO[v["invoke"]] + (". With `--report`: you or the user" if v.get("report_invoke") == "model" else "")
        doc = f"[{v['doc']}]({v['doc']})" if v.get("doc") else "`--help`"
        rows.append(f"| `{v['id']}` | {v['category']} | {v['line']} | {who} | {doc} |")
    return "\n".join([START, *rows, END])


def main(argv: list[str]) -> int:
    path = ROOT / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    a, b = text.index(START), text.index(END) + len(END)
    new = text[:a] + table() + text[b:]
    if "--check" in argv:
        if new != text:
            print("SKILL.md: the verb table differs from commands.json; run scripts/gen_router.py")
            return 1
        print("SKILL.md verb table matches commands.json")
        return 0
    path.write_text(new, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
