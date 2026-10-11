"""understando signals and the bare menu.

    understando signals [--json] [--pr-head SHA]
    understando menu [--all]                      one question: two or three recommended verbs. --all adds the verb table

The PR head comes from --pr-head, then $UNDERSTANDO_PR_HEAD, then `gh pr view` (skipped when
$UNDERSTANDO_OFFLINE is set). Without it, freshness is unknown. The menu never runs a verb.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ctx as context  # noqa: E402
import discover  # noqa: E402
import journal  # noqa: E402

CLOSED = ("Formal", "Proven", "Backed")


def ready_changes(c: context.Ctx, data: dict, branch: str | None, tip: str | None) -> dict:
    """What the ready branch changed after the map: the files, and the claims and verifiers whose
    code, test or formal artifact is one of them. Those can be verified again at the ready tip."""
    out = {"branch": branch, "tip": tip, "since": None, "changed": [], "claims": [], "verifiers": []}
    if not (c.repo and tip and data):
        return out
    since = (data.get("ready") or {}).get("head") or data["head"]
    if since == tip:
        since = data["head"]
    out["since"] = since
    import config
    import repoinfo
    cfg = config.load(repoinfo.repo_name(c.repo))
    diff = subprocess.run(["git", "-C", str(c.repo), "diff", "--name-only", "--no-renames", data["head"], tip, "--", ".",
                           *config.pathspec_excludes(cfg)], capture_output=True, text=True)
    changed = sorted(p for p in diff.stdout.splitlines() if p)
    out["changed"] = changed
    if not changed:
        return out
    hit = set(changed)

    def touches(paths: list[str]) -> bool:
        return any(p in hit or any(h.endswith("/" + p) or p.endswith("/" + h) for h in hit) for p in paths if p)

    code_hit = {cl["id"] for cl in data["claims"] if touches([r["path"] for r in cl.get("code", [])])}
    vids, claims = set(), set(code_hit)
    for v in data["verifiers"]:
        drift = (v.get("formal_record") or {}).get("drift") or {}
        paths = [(v.get("formal") or {}).get("artifact", "")] + [m["path"] for m in drift.get("model_files", []) + drift.get("code_files", [])]
        cmd = v.get("command") or {}
        cwd = cmd.get("cwd", ".").strip("./")
        paths += [f"{cwd}/{a.split('::')[0]}" if cwd else a.split("::")[0] for a in cmd.get("argv", []) if "/" in a or a.endswith(".py")]
        if touches(paths):
            vids.add(v["id"])
            claims |= set(v["claims"])
        elif set(v["claims"]) & code_hit:
            vids.add(v["id"])
    out["claims"] = sorted(claims, key=lambda x: (len(x), x))
    out["verifiers"] = sorted(vids)
    return out


LOC = re.compile(r"([\w./-]+\.[A-Za-z]+):(\d+(?:-\d+)?(?:,\s*\d+(?:-\d+)?)*)")
SHA = re.compile(r"\bat ([0-9a-f]{7,40})\b")


def _ranges(spec: str) -> list[tuple[int, int]]:
    out = []
    for part in re.split(r",\s*", spec):
        a, _, b = part.partition("-")
        out.append((int(a), int(b or a)))
    return out


def bug_locations(inv: dict, bug: dict) -> list[tuple[str, list[tuple[int, int]]]]:
    """The code locations of a possible bug: its `where`, else the file:line refs in the invariant's evidence."""
    if bug.get("where"):
        return [(m.group(1), _ranges(m.group(2))) for m in LOC.finditer(bug["where"])]
    # An evidence row that starts with a code path. The "test ..." and "control ..." rows are not code.
    return [(m.group(1), _ranges(m.group(2))) for e in inv.get("evidence", []) if isinstance(e, str) and (m := LOC.match(e))]


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else ""


def _resolve_path(repo: Path, ref: str, path: str, cache: dict) -> str | None:
    if ref not in cache:
        cache[ref] = _git(repo, "ls-tree", "-r", "--name-only", ref).splitlines()
    files = cache[ref]
    if path in files:
        return path
    hits = [f for f in files if f.endswith("/" + path)]
    return hits[0] if len(hits) == 1 else None


def _hunks(repo: Path, base: str, tip: str, path: str) -> list[tuple[int, int]]:
    """The old-side line ranges that `base..tip` changes in `path`."""
    out = []
    for m in re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@", _git(repo, "diff", "-U0", "--no-renames", base, tip, "--", path), re.M):
        start, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        out.append((start, start + max(n, 1) - 1))
    return out


def bug_changes(c: context.Ctx, data: dict, tip: str | None) -> list[dict]:
    """For each possible bug: did the -ready branch change its code after the answer? A user answer
    that disagreed with the code at the map head may be fixed on -ready; then discover is stale and
    the next step is a re-check (map + probe on the changed code)."""
    rows: list[dict] = []
    if not (c.repo and data):
        return rows
    cache: dict = {}
    for inv in data.get("invariants", []):
        for bug in inv.get("possible_bug") or []:
            m = SHA.search(bug.get("where", ""))
            base = bug.get("at_commit") or (m.group(1) if m else None) or data["head"]
            base = (_git(c.repo, "rev-parse", "-q", "--verify", base + "^{commit}").strip() or data["head"])
            row = {"invariant": inv["id"], "question": bug.get("question", ""), "base": base, "where": [], "changed": False,
                   "commits": [], "claims": sorted({cl["id"] for cl in data["claims"] if cl.get("invariant") == inv["id"]},
                                                   key=lambda x: (len(x), x))}
            for path, ranges in bug_locations(inv, bug):
                full = _resolve_path(c.repo, base, path, cache)
                if not full:
                    continue
                row["where"].append(f"{full}:{','.join(f'{a}-{b}' if a != b else str(a) for a, b in ranges)}")
                if not tip or tip == base:
                    continue
                hit = any(a <= he + 2 and he_s - 2 <= b for a, b in ranges for he_s, he in _hunks(c.repo, base, tip, full))
                if hit:
                    row["changed"] = True
                    row["commits"] += [x for x in _git(c.repo, "log", "--format=%h", "--reverse", f"{base}..{tip}", "--", full).split()
                                       if x not in row["commits"]]
                    row["claims"] = sorted(set(row["claims"]) | {cl["id"] for cl in data["claims"]
                                                                 if any(r.get("path", "").endswith(full) or full.endswith(r.get("path", "\0"))
                                                                        for r in cl.get("code", []))}, key=lambda x: (len(x), x))
            rows.append(row)
    return rows


def review_hint(c: context.Ctx) -> dict | None:
    """The PR to review from the cwd: a repo with a run folder for an open PR."""
    import config
    import repoinfo
    root = repoinfo.repo_root(Path.cwd())
    if not root:
        return None
    base = config.runs_root() / repoinfo.repo_name(root)
    prs = sorted((p.name for p in base.glob("*") if p.is_dir() and p.name.isdigit()), key=int, reverse=True) if base.is_dir() else []
    if not prs or os.environ.get("UNDERSTANDO_OFFLINE"):
        return None
    slug = repoinfo.slug(repoinfo.origin_url(root))
    for n in prs:
        info = repoinfo.gh_pr(n, slug, "state")
        if info and str(info.get("state", "")).upper() == "OPEN":
            return {"pr": n, "repo": str(root), "run": str(base / n)}
    return None


def review_branch_hint() -> dict | None:
    """A fetched review branch (understando/<pr>-review) in the repo of the cwd: the reviewer's path."""
    import repoinfo
    root = repoinfo.repo_root(Path.cwd())
    if not root:
        return None
    refs = subprocess.run(["git", "-C", str(root), "for-each-ref", "--format=%(refname)", "refs/remotes/origin/understando/", "refs/heads/understando/"],
                          capture_output=True, text=True).stdout.split()
    prs = sorted({m.group(1) for r in refs if (m := re.search(r"understando/(\d+)-review$", r))}, key=int, reverse=True)
    return {"pr": prs[0], "repo": str(root)} if prs else None


def pr_head(data: dict | None, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    if os.environ.get("UNDERSTANDO_PR_HEAD"):
        return os.environ["UNDERSTANDO_PR_HEAD"]
    if not data or os.environ.get("UNDERSTANDO_OFFLINE") or not shutil.which("gh") or "/" not in str(data.get("repo", "")):
        return None
    try:
        out = subprocess.run(["gh", "pr", "view", str(data["pr"]), "-R", data["repo"], "--json", "headRefOid", "-q", ".headRefOid"],
                             capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return None
    return out.stdout.strip() or None


def collect(c: context.Ctx, explicit_head: str | None = None) -> dict:
    data = c.data()
    state = context.load_mode()
    rows = journal.read(c.journal)
    sig: dict = {"mode": {"on": bool(state.get("on")), "run": state.get("run"), "repo": state.get("repo"), "pr": state.get("pr")},
                 "run": str(c.run) if c.run else None, "ledger": {"rows": len(rows), "prompts": sum(r.get("kind") == "prompt" for r in rows)},
                 "toolchains": context.tool_status()}
    if not data:
        sig["trust_map"] = {"present": False}
        return sig
    head = pr_head(data, explicit_head)
    sig["trust_map"] = {"present": True, "head": data["head"], "pr_head": head,
                        "fresh": None if head is None else head == data["head"], "summary": data.get("summary")}
    open_: dict[str, list[str]] = {}
    for cl in data["claims"]:
        if cl.get("verdict") not in CLOSED and not cl.get("waiver"):
            open_.setdefault(cl.get("verdict") or "unrated", []).append(cl["id"])
    sig["open_claims"] = open_
    sig["waived"] = [cl["id"] for cl in data["claims"] if cl.get("waiver")]
    ran = [(k.get("result") or {}).get("ran_at") for k in data["controls"] if not (k.get("result") or {}).get("recorded")]
    sig["last_probe"] = data.get("probed_at") or max([r for r in ran if r], default=None)
    untested = [v["id"] for v in data["verifiers"] if "command" in v and v.get("state") in (None, "untested")]
    sig["untested_verifiers"] = untested
    mix: dict[str, int] = {}
    for cl in data["claims"]:
        key = str(cl.get("tier") or "none")
        mix[key] = mix.get(key, 0) + 1
    sig["tier_mix"] = mix
    sig["formal_targets"] = [cl["id"] for cl in data["claims"] if (cl.get("tier_target") or 0) >= 4 and cl.get("verdict") != "Formal"]
    ready_p = c.run / "ready.json"
    if ready_p.is_file():
        r = json.loads(ready_p.read_text())
        sig["gates"] = {"head": r["head"], "stale": r["head"] != data["head"], "pass": r["pass"],
                        **{f"gate{g['n']}": g["pass"] for g in r["gates"]}}
    else:
        sig["gates"] = None
    trim_p = c.run / "trim.json"
    sig["trim"] = {"ran": trim_p.is_file() and json.loads(trim_p.read_text()).get("head") == data["head"]}
    exp = c.run / "explainer.mdx"
    sig["explainer"] = {"present": exp.is_file(), "stale": exp.is_file() and exp.stat().st_mtime < c.map.stat().st_mtime}
    if c.repo:
        import config
        import repoinfo
        cfg = config.load(repoinfo.repo_name(c.repo))
        branch = cfg["ready_branch"].format(pr=data.get("pr"))
        tip = repoinfo.rev(c.repo, f"refs/remotes/origin/{branch}") or repoinfo.rev(c.repo, f"refs/heads/{branch}")
        local = repoinfo.rev(c.repo, f"refs/heads/{branch}")
        sig["ready_branch"] = {**({"reverify": ready_changes(c, data, branch, tip)} if tip else {"reverify": None}),
                               "branch": branch, "tip": tip, "local": local,
                               "local_behind_origin": bool(tip and local and tip != local)}
    d = discover.status(c)
    sig["discover"] = {"candidates": d["candidates"], "open": len(d["open"]), "open_ids": d["open"][:12],
                       "possible_bugs": d["possible_bugs"], "proposed": d["proposed"],
                       "bug_changes": bug_changes(c, data, (sig.get("ready_branch") or {}).get("tip"))}
    return sig


def ids(xs: list[str], n: int = 6) -> str:
    return ", ".join(xs[:n]) + (f" and {len(xs) - n} more" if len(xs) > n else "")


def recommend(sig: dict, data: dict | None = None) -> list[dict]:
    """Two or three next verbs. Each reason names the concrete cause in plain words; the IDs, SHAs
    and paths go in a trailing "(ref: ...)" part. Paused verbs never appear."""
    import names
    data = data or {}
    nm = lambda i: names.of(data, i)  # noqa: E731
    picks: list[dict] = []

    def add(verb: str, why: str, label: str | None = None, command: str | None = None) -> None:
        if verb not in [p["verb"] for p in picks]:
            picks.append({"verb": verb, "why": why, "label": label or verb, "command": command or f"understando {verb}"})

    hint = sig.get("review_hint")
    if hint:
        picks.append({"verb": "review", "label": f"review {hint['pr']}", "command": f"understando review {hint['pr']}",
                      "why": f"PR #{hint['pr']} is open and has a run folder. review shows its state and asks one question."})
    rb = sig.get("review_branch_hint")
    if rb and not hint:
        picks.append({"verb": "open", "label": f"open {rb['pr']}", "command": f"understando open {rb['pr']}",
                      "why": f"The review branch of PR #{rb['pr']} is here. open shows its explainer and walks you through it."})
    tmap = sig["trust_map"]
    if not tmap["present"]:
        if not hint and not rb:
            add("build", "No open PR with a run folder, and no review branch here. build starts new work verifier first.")
        add("map", "No trust map exists for this run yet. map writes the claim ledger first.")
        add("discover", "No invariant was found with the user yet. Find them before any verifier is written.")
        add("doctor", "Check the setup before the first run.")
        return picks[:3]
    d = sig["discover"]
    fixed = [b for b in d.get("bug_changes", []) if b["changed"]]
    unfixed = [b for b in d.get("bug_changes", []) if not b["changed"]]
    rv = (sig.get("ready_branch") or {}).get("reverify") or {}
    if fixed:
        b = fixed[0]
        add("map", f"Runs map + probe on the changed code. The review branch changed the code of the possible bug '{nm(b['invariant'])}' "
                   f"after your answer" + (f"; {names.listing([nm(x) for x in b['claims']])} use it" if b["claims"] else "") + "."
                   + names.ref([b["invariant"], *b["where"], *b["commits"], *b["claims"]], 10),
            label=f"Re-check the fix for '{nm(b['invariant'])}'")
    elif rv.get("claims"):
        add("map", f"The review branch changed the code or checks of {names.listing([nm(x) for x in rv['claims']])}: "
                   "map + probe verify them again at the review-branch tip." + names.ref(rv["claims"] + rv["verifiers"], 10),
            label="Re-check the changed code")
    if tmap.get("fresh") is False:
        add("map", "The PR head moved after the last map." + names.ref([tmap["head"][:10], tmap["pr_head"][:10]]))
    if unfixed:
        add("discover", f"The possible bug '{nm(unfixed[0]['invariant'])}': your answer disagrees with the code, and the review branch "
                        "did not change that code." + names.ref([b["invariant"] for b in unfixed] + unfixed[0]["where"]),
            label=f"Discover: '{nm(unfixed[0]['invariant'])}'")
    elif d["possible_bugs"] and not fixed:
        add("discover", f"{len(d['possible_bugs'])} of your answers disagree with the code." + names.ref([x.split()[0] for x in d["possible_bugs"]]))
    elif d["open"]:
        add("discover", f"{len(d['open'])} invariant candidates wait for your decision." + names.ref(d.get("open_ids") or []))
    elif not d["candidates"]:
        add("discover", "No invariant was found with the user yet.")
    if not sig["last_probe"]:
        add("probe", "No control ran yet.")
    elif sig["untested_verifiers"]:
        add("probe", f"{names.listing([nm(x) for x in sig['untested_verifiers']])} have no control result." + names.ref(sig["untested_verifiers"]))
    open_ids = [i for v in sig["open_claims"].values() for i in v]
    if open_ids:
        add("close", f"Open claims: {names.listing([nm(x) for x in open_ids])}." + names.ref(open_ids), label=f"Close '{nm(open_ids[0])}'")
    if not sig["trim"]["ran"]:
        add("trim", "trim did not run at this head: excess code and doubled unit tests are unknown.")
    if not sig["gates"] or sig["gates"]["stale"] or not sig["gates"]["pass"]:
        failing = [k.replace("gate", "gate ") for k, v in (sig["gates"] or {}).items() if k.startswith("gate") and not v]
        add("ready", "The four gates were not computed at this head." if not sig["gates"] or sig["gates"]["stale"]
            else f"{', '.join(failing)} fail at this head. `ready --report` shows why.", command="understando ready --report")
    if not sig["explainer"]["present"] or sig["explainer"]["stale"]:
        add("explain", "The explainer is missing, or older than the trust map.")
    if sig["formal_targets"]:
        add("formalize", f"{names.listing([nm(x) for x in sig['formal_targets']])} target a model check or a proof." + names.ref(sig["formal_targets"]))
    return picks[:3]


def table(cmds: dict) -> str:
    who = {"model": "you or the agent", "user": "you only", "hook": "a hook only"}
    lines = []
    for cat in cmds["categories"]:
        verbs = [v for v in cmds["verbs"] if v["category"] == cat]
        if not verbs:
            continue
        lines.append(f"\n{cat}")
        for v in verbs:
            flag = (" (paused)" if v.get("paused") else "") + ("" if v.get("tier", "entry") == "entry" else f" ({v['tier']})")
            by = who[v["invoke"]] + ("; --report: you or the agent" if v.get("report_invoke") == "model" else "") \
                + ("; --approve: you only" if v.get("approve_invoke") == "user" else "")
            lines.append(f"  {v['id']:<10} {v['line']}{flag}  [{by}]")
    lines.append("\nAliases: " + ", ".join(f"{a} -> {b}" for a, b in cmds["aliases"].items()) + " (deprecated)")
    return "\n".join(lines)


def situation(sig: dict) -> list[str]:
    tmap = sig.get("trust_map") or {}
    if not tmap.get("present"):
        return [f"Run folder {sig.get('run') or 'none'}: no trust map yet."]
    lines = []
    lines.append("The PR head is " + ("unknown" if tmap.get("pr_head") is None else
                 ("the map head" if tmap.get("fresh") else "newer than the map")) + ".")
    summ = tmap.get("summary") or {}
    words = [("Formal", "proven formally"), ("Proven", "proven by tests"), ("Backed", "backed but not proven"),
             ("Asserted", "only stated"), ("Gap", "not checked")]
    if summ:
        lines.append("Now: " + ", ".join(f"{summ[k]} {w}" for k, w in words if summ.get(k)) + ".")
    return lines


def menu(c: context.Ctx, explicit_head: str | None = None, show_all: bool = False) -> int:
    import prompt
    sig = collect(c, explicit_head)
    sig["review_hint"] = review_hint(c)
    sig["review_branch_hint"] = review_branch_hint()
    picks = recommend(sig, c.data())
    cmds = context.commands()
    q = prompt.make(situation(sig), "What next?",
                    [prompt.option(p["label"], p["why"], p["command"]) for p in picks],
                    else_does="Name a verb, or say \"all verbs\" for the full list. Nothing runs until you choose.")
    payload = {"recommend": picks, "prompt": q, "signals": sig, **({"verbs": cmds["verbs"]} if show_all else {})}
    text = prompt.render(q) + ("\n" + table(cmds) if show_all else "")
    context.emit(c, payload, text)
    return 0
