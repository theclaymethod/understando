"""understando routes: which skill or rule each routed step uses on this machine.

    understando routes [--json]

One rule for every route: when the original skill is installed, use it; else use understando's
adapted copy (references/adapted/, listed in manifest.json); else the built-in fallback line. A
required piece (asd-ste100, the explainer runtime) that is missing is a setup problem. asd-ste100
is required with no adapted copy and no built-in fallback: every text that a reviewer or the user
reads is written by applying it, and scripts/ste.py runs its lint as the mechanical gate. When the
mode state says that Poteto Mode is active (`understando mode on --with poteto-mode`), it owns the
reply style, the subagent rules and autonomy. understando keeps only its exceptions: discover,
claim wording and waivers stop for the user.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import ctx as context  # noqa: E402
import tm  # noqa: E402

SKILL_HOMES = [".agents/skills", ".claude/skills", ".claude/skills/pstack/skills", ".codex/skills", ".cursor/skills"]
MANIFEST = tm.ROOT / "references" / "adapted" / "manifest.json"
EXCEPTIONS = "discover, claim wording and waivers stop for the user"


def home() -> Path:
    return Path(os.environ.get("HOME") or str(Path.home()))


def find_skill(name: str) -> Path | None:
    h = home()
    for d in SKILL_HOMES:
        if (h / d / name / "SKILL.md").is_file():
            return h / d / name
    for p in sorted((h / ".claude" / "plugins" / "cache").glob(f"*/*/*/skills/*/{name}/SKILL.md")):
        return p.parent
    return None


def installed_version(path: Path) -> str | None:
    """The version of an installed original: a plugin cache folder name, or a version field."""
    real = path.resolve()
    m = re.search(r"/(\d+\.\d+\.\d+)/", str(real))
    if m:
        return m.group(1)
    for parent in [real, *real.parents][:5]:
        for meta in (parent / ".claude-plugin" / "plugin.json", parent / "package.json", parent / "plugin.json"):
            if meta.is_file():
                try:
                    v = json.loads(meta.read_text()).get("version")
                except (json.JSONDecodeError, OSError):
                    v = None
                if v:
                    return str(v)
    return None


def newer(a: str | None, b: str | None) -> bool:
    """True when version a is newer than b. Unparsable versions compare as equal."""
    def parts(v: str | None):
        return tuple(int(x) for x in re.findall(r"\d+", v or "")) or None
    pa, pb = parts(a), parts(b)
    return bool(pa and pb and pa > pb)


def manifest() -> dict[str, dict]:
    if not MANIFEST.is_file():
        return {}
    return {m["original_skill"]: m for m in json.loads(MANIFEST.read_text(encoding="utf-8"))}


def resolve_all() -> list[dict]:
    copies = manifest()
    state = context.load_mode()
    owners = state.get("with") or []
    out = []
    for r in context.commands().get("routes", []):
        name = r["skill"]
        found = find_skill(name)
        copy = copies.get(name)
        row = {"skill": name, "for": r["for"], "verbs": r.get("verbs", []), "required": bool(r.get("required"))}
        if r.get("apply"):
            row["apply"] = r["apply"]
        if found:
            row.update(use="original", path=str(found), version=installed_version(found))
            if copy and newer(row["version"], copy.get("source_version")):
                row["drift"] = f"the installed {name} is {row['version']}; the adapted copy is from {copy.get('source_version')}"
        elif copy and not r.get("no_fallback") and (tm.ROOT / copy["file"]).is_file():
            row.update(use="adapted", path=copy["file"])
        elif r.get("required"):
            row.update(use="missing", fix="run understando setup")
        else:
            row.update(use="built-in", rule=r.get("fallback", "skip this route; the step works without it"))
        out.append(row)
    if "poteto-mode" in owners:
        out.insert(0, {"skill": "poteto-mode", "for": "owner of the reply style, the subagent rules and autonomy",
                       "use": "active", "verbs": ["*"], "defer": True, "exceptions": EXCEPTIONS})
    return out


def text(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        if r.get("defer"):
            lines.append(f"poteto-mode is active: it owns the reply style, the subagent rules and autonomy. understando defers to it, except: {EXCEPTIONS}.")
            continue
        where = {"original": f"skill {r['skill']} ({r.get('path')})", "adapted": f"adapted copy {r.get('path')}",
                 "built-in": f"built-in: {r.get('rule')}", "missing": f"MISSING, required: {r.get('fix')}"}[r["use"]]
        lines.append(f"{r['skill']:<44} {where}  [{r['for']}]" + (f"  drift: {r['drift']}" if r.get("drift") else "")
                     + (f"\n{'':<44} apply: {r['apply']}" if r.get("apply") and r["use"] == "original" else ""))
    return "\n".join(lines)


def main(c: context.Ctx, argv: list[str]) -> int:
    rows = resolve_all()
    context.emit(c, {"routes": rows}, text(rows))
    return 0
