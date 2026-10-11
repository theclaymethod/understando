"""understando signals and the bare menu.

    understando signals [--json] [--pr-head SHA]
    understando menu                              two or three recommended verbs, then the full table

The PR head comes from --pr-head, then $UNDERSTANDO_PR_HEAD, then `gh pr view` (skipped when
$UNDERSTANDO_OFFLINE is set). Without it, freshness is unknown. The menu never runs a verb.
"""

from __future__ import annotations

import json
import os
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
    sig["discover"] = {"candidates": d["candidates"], "open": len(d["open"]), "possible_bugs": d["possible_bugs"], "proposed": d["proposed"]}
    return sig


def recommend(sig: dict) -> list[dict]:
    """Two or three next verbs, with one-line reasons. Paused verbs never appear."""
    picks: list[dict] = []

    def add(verb: str, why: str) -> None:
        if verb not in [p["verb"] for p in picks]:
            picks.append({"verb": verb, "why": why, "command": f"understando {verb}"})

    hint = sig.get("review_hint")
    if hint:
        picks.append({"verb": "review", "why": f"PR #{hint['pr']} is open and has a run folder: one line runs the whole review.",
                      "command": f"understando review {hint['pr']}"})
    tmap = sig["trust_map"]
    rv = (sig.get("ready_branch") or {}).get("reverify") or {}
    if tmap["present"] and rv.get("claims"):
        add("map", f"The ready branch changed the code or checks of {', '.join(rv['claims'][:6])}: map, probe and formalize can verify them again.")
    if not tmap["present"]:
        add("map", "No trust map exists for this run yet.")
        add("discover", "Find the invariants with the user before you write any verifier.")
        add("doctor", "Check the setup before the first run.")
        return picks[:3]
    if tmap.get("fresh") is False:
        add("map", f"The PR head moved from {tmap['head'][:10]} to {tmap['pr_head'][:10]}.")
    d = sig["discover"]
    if d["possible_bugs"]:
        add("discover", f"{len(d['possible_bugs'])} user answers disagree with the code: possible bugs.")
    elif d["open"]:
        add("discover", f"{d['open']} invariant candidates wait for a user decision.")
    elif not d["candidates"]:
        add("discover", "No invariant was found with the user yet.")
    if not sig["last_probe"] or sig["untested_verifiers"]:
        add("probe", "No control ran yet." if not sig["last_probe"] else f"{len(sig['untested_verifiers'])} verifiers have no control result.")
    n_open = sum(len(v) for v in sig["open_claims"].values())
    if n_open:
        add("close", f"{n_open} claims are open: " + ", ".join(f"{len(v)} {k}" for k, v in sig["open_claims"].items()) + ".")
    if not sig["trim"]["ran"]:
        add("trim", "trim did not run at this head: excess code and doubled unit tests are unknown.")
    if not sig["gates"] or sig["gates"]["stale"] or not sig["gates"]["pass"]:
        add("ready", "The four gates did not pass at this head. `ready --report` shows why.")
    if not sig["explainer"]["present"] or sig["explainer"]["stale"]:
        add("explain", "The explainer is missing, or older than the trust map.")
    if sig["formal_targets"]:
        add("formalize", f"{len(sig['formal_targets'])} claims target tier 4 or 5.")
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
            flag = " (paused)" if v.get("paused") else ""
            by = who[v["invoke"]] + ("; --report: you or the agent" if v.get("report_invoke") == "model" else "") \
                + ("; --approve: you only" if v.get("approve_invoke") == "user" else "")
            lines.append(f"  {v['id']:<10} {v['line']}{flag}  [{by}]")
    lines.append("\nAliases: " + ", ".join(f"{a} -> {b}" for a, b in cmds["aliases"].items()) + " (deprecated)")
    return "\n".join(lines)


def menu(c: context.Ctx, explicit_head: str | None = None) -> int:
    sig = collect(c, explicit_head)
    sig["review_hint"] = review_hint(c)
    picks = recommend(sig)
    cmds = context.commands()
    payload = {"recommend": picks, "signals": sig, "verbs": cmds["verbs"]}
    text = ["understando: recommended next"] + [f"  {i}. {p['command']}  {p['why']}" for i, p in enumerate(picks, 1)]
    text.append("Nothing runs until you choose one.")
    context.emit(c, payload, "\n".join(text) + "\n" + table(cmds))
    return 0
