"""Tests that the ready branch added, and the claim that each one most likely checks.

map lists them; review asks the user to link each one (one question per test). A linked test
becomes a verifier at the ready tip, with one control: `restore-file` puts back the code that the
ready branch changed (the fix), as it was at the map head. probe then runs the test and its
control, and the claim moves only after that run. A claim never takes an old test as evidence of
a new fix: the old test does not check the new case.

A proposal: {"test": selector, "file", "words": the test name as words, "claim", "score",
"argv", "cwd", "fix_files", "from": the map head}. The command copies a verifier of the map that
runs the same test file (or the same runner), so it stays inside the approved CI profile.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

TEST_FILE = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*\.py$|_test\.(py|go)$|\.(test|spec)\.[jt]sx?$")
STOP = {"a", "an", "the", "of", "to", "that", "and", "or", "is", "it", "its", "in", "on", "no", "not", "by", "for", "with", "be", "test"}


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else ""


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", re.sub(r"(?<!^)(?=[A-Z])", " ", text).lower()) if w not in STOP and len(w) > 2}


def added_tests(repo: Path, base: str, tip: str) -> list[dict]:
    """The test functions and classes that base..tip adds, with their file."""
    out = []
    files = [f for f in _git(repo, "diff", "--name-only", "--diff-filter=AM", base, tip).splitlines() if TEST_FILE.search(f)]
    for f in files:
        old = _git(repo, "show", f"{base}:{f}")
        new = _git(repo, "show", f"{tip}:{f}")
        cls = None
        for line in new.splitlines():
            m = re.match(r"class (\w*Test\w*)\b", line)
            if m:
                cls = m.group(1)
                if not re.search(rf"^class {cls}\b", old, re.M):
                    out.append({"file": f, "kind": "class", "name": cls, "class": cls})
                continue
            m = re.match(r"(\s*)(?:async\s+)?def (test_\w+)", line)
            if m and not re.search(rf"def {m.group(2)}\b", old):
                if m.group(1) and cls and any(t["name"] == cls for t in out):
                    continue
                out.append({"file": f, "kind": "function", "name": m.group(2), "class": cls if m.group(1) else None})
    return out


def _selector(t: dict, sibling_argv: list[str], cwd: str) -> list[str] | None:
    """The argv that runs the test, from a verifier command that runs a test of the same runner."""
    rel = t["file"][len(cwd) + 1:] if cwd and t["file"].startswith(cwd + "/") else t["file"]
    last = sibling_argv[-1]
    if "::" in last or last.endswith(".py") and "unittest" not in sibling_argv:
        sel = rel + ("::" + t["class"] if t.get("class") else "") + ("::" + t["name"] if t["kind"] == "function" else "")
        return [*sibling_argv[:-1], sel]
    if "unittest" in sibling_argv and re.fullmatch(r"[\w.]+", last):
        mod = rel[:-3].replace("/", ".")
        return [*sibling_argv[:-1], mod + ("." + (t["class"] or "") if t.get("class") else "")
                + ("." + t["name"] if t["kind"] == "function" and t.get("class") else "")]
    return None


def proposals(c, data: dict, tip: str | None, base: str | None = None) -> list[dict]:
    """One proposal per test that the ready branch added and that no verifier runs yet."""
    if not (c.repo and tip and data):
        return []
    base = base or data["head"]
    if base == tip:
        return []
    tests = added_tests(c.repo, base, tip)
    if not tests:
        return []
    fix_files = [f for f in _git(c.repo, "diff", "--name-only", "--no-renames", base, tip).splitlines()
                 if f and not TEST_FILE.search(f) and re.search(r"\.(py|ts|tsx|js|mjs|rs|go)$", f)]
    known = " ".join(" ".join((v.get("command") or {}).get("argv", [])) for v in data["verifiers"])
    whole = set()   # test files that a verifier runs as a whole (a file path, or a dotted module)
    for v in data["verifiers"]:
        for a in (v.get("command") or {}).get("argv", [])[1:]:
            if a.endswith(".py") and "::" not in a:
                whole.add(a)
            elif re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)+", a) and not re.search(r"\.[A-Z]\w*(\.test_\w+)?$", a):
                whole.add(a.replace(".", "/") + ".py")
    out = []
    for t in tests:
        if re.search(rf"\b{re.escape(t['name'])}\b", known) or any(t["file"].endswith(w) for w in whole):
            continue
        tw = words(t["name"])
        best, score = None, 0.0
        for cl in data["claims"]:
            text = " ".join([cl.get("name", ""), (cl.get("plain") or {}).get("what", ""), cl.get("text", "")])
            cw = words(text)
            s = len(tw & cw) / max(len(tw), 1)
            if any(fix.endswith(r["path"]) or r["path"].endswith(fix) for fix in fix_files for r in cl.get("code", [])):
                s += 0.5
            if s > score:
                best, score = cl, s
        # A test check is the best model for the command of a new test; a static check comes last.
        ordered = sorted((v for v in data["verifiers"] if "command" in v), key=lambda v: v["kind"] not in ("unit", "integration", "e2e", "property", "fuzz"))
        sib = next((v for v in ordered if any(t["file"].endswith(a.split("::")[0]) for a in v["command"]["argv"])), None) \
            or next((v for v in ordered if _selector(t, v["command"]["argv"], v["command"].get("cwd", ".").strip("./"))), None)
        cwd = (sib or {}).get("command", {}).get("cwd", ".")
        argv = _selector(t, sib["command"]["argv"], cwd.strip("./")) if sib else None
        out.append({"test": t["name"], "file": t["file"], "words": t["name"].removeprefix("test_").replace("_", " "),
                    "claim": best["id"] if best and score >= 0.3 else None, "score": round(score, 2),
                    "argv": argv, "cwd": cwd, "sibling": (sib or {}).get("id"), "fix_files": fix_files, "from": base, "tip": tip})
    return out


def report(c, data: dict) -> list[str]:
    import config
    import repoinfo
    cfg = config.load(repoinfo.repo_name(c.repo))
    branch = cfg["ready_branch"].format(pr=data.get("pr"))
    tip = repoinfo.rev(c.repo, f"refs/heads/{branch}") or repoinfo.rev(c.repo, f"refs/remotes/origin/{branch}")
    out = []
    for p in proposals(c, data, tip):
        cl = next((x for x in data["claims"] if x["id"] == p["claim"]), None)
        out.append(f"map: the ready branch adds the test {p['test']} ({p['file']}); "
                   + (f"it most likely checks {p['claim']} ({cl.get('name')}). review asks you to link it." if cl else "no claim matches it."))
    return out


def link(data: dict, p: dict, by: str) -> dict:
    """Add the verifier and its control for a confirmed proposal. Returns the verifier."""
    import ops
    import tm
    vid = ops.next_id(data, "V")
    kind = "integration"
    v = {"id": vid, "kind": kind, "claims": [p["claim"]], "tier": "fact",
         "description": f"The test {p['test']} that the ready branch added. It runs at the ready tip.",
         "command": {"argv": p["argv"], "cwd": p["cwd"], "timeout_s": 900},
         "independence": {"by": "tool", "tool": p["argv"][0]}, "cost": {"usd": 0},
         "provenance": f"{p['file']} on the ready branch; linked in review by {by}", "at": p["tip"],
         "link": {"source": p["file"], "by": by, "at": tm.now(), "fix_from": p["from"]},
         "name": "the new " + " ".join(re.sub(r"(?<!^)(?=[A-Z])", " ", p["test"].removeprefix("test_")).replace("_", " ").lower().replace(" test", "").split()[:3]) + " test"}
    sib = next((x for x in data["verifiers"] if x["id"] == p.get("sibling")), None)
    if sib and (sib.get("command") or {}).get("env_file"):
        v["command"]["env_file"] = True
    data["verifiers"].append(v)
    if p["fix_files"]:
        data["controls"].append({"id": ops.next_id(data, "K"), "verifier": vid, "recipe": "remove-covered-code",
                                 "description": "Put back the code as it was before the fix on the ready branch.",
                                 "edits": [{"op": "restore-file", "path": f, "at": p["from"]} for f in p["fix_files"]],
                                 "expect": {"status": "red"}})
    return v
