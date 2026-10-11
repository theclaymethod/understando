"""understando review: a full PR review from one line. `understando review <pr>`.

    understando review N [--head SHA]            resolve, set up, then ask one question (the prompt)
    understando review N --go                    run the next stop (its steps chain), then ask the next question
    understando review N --through               run every stop that is left ("run through")
    understando review N --full                  also print the full state (the old summary)
    understando review N --answers FILE          the user's answers as a file (the e2e test, or a scripted run)
    understando review N --guard PATH[,PATH]     before a hand edit on the ready branch: may this file change now?

It derives the context from the PR number alone:
  1. the repo: the main checkout of the cwd git root (--repo overrides);
  2. owner/repo: `git remote get-url origin`;
  3. the PR head and base: `gh pr view N --json headRefOid,baseRefName` (else --head);
  4. the run folder: <runs root>/<repo name>/<N> (UNDERSTANDO_RUNS sets the runs root);
  5. the ready branch (`ready_branch` of understando.toml, default understando/<N>-ready) and its
     worktree under <repo>/<worktree_root>/understando-<N>-ready. A missing worktree starts at the
     ready branch (from origin when it is there), else at the PR head. A present one pulls with --no-rebase.

Then: mode on, ci (ci.json), signals, doctor, and one question. `--json` puts it in `prompt`:
{situation: [<= 5 lines], next: {step, does, scope, cost, time, writes}, question,
 options: [{id, label, does, run?, recommended?}]}. The agent renders it as text and asks it.

The steps chain into four stops: (1) map + probe on the changed code (+ formal, only when a formal
check must run again), (2) close, one claim per question, (3) trim, (4) ready --report + explain.
"run through" skips the stops that need no decision. These stops stay in every mode: the CI
approval, each close choice (claim wording and waivers), and each paid step. explain prints
pr-section.md; nothing edits the PR.

Answer file: {"go": "step" | "run through", "ci": "approve", "close": {"answers": [...]},
"paid": ["V36"]}. Write "ci": "approve" and "paid" only after a clear yes from the user.
State: $R/review.json.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci  # noqa: E402
import config  # noqa: E402
import ctx as context  # noqa: E402
import journal  # noqa: E402
import lock  # noqa: E402
import offline  # noqa: E402
import repoinfo  # noqa: E402
import tm  # noqa: E402

STEPS = ["map", "probe", "formal", "close", "trim", "ready", "explain"]
STAGES = [("check", ["map", "probe", "formal"]), ("close", ["close"]), ("trim", ["trim"]), ("ship", ["ready", "explain"])]
STAGE_NAME = {"check": "map + probe on the changed code", "close": "close", "trim": "trim", "ship": "ready + explain"}
CLOSED = ("Formal", "Proven", "Backed")


def state_path(run: Path) -> Path:
    return run / "review.json"


def load_state(run: Path) -> dict:
    p = state_path(run)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def save_state(run: Path, st: dict) -> None:
    state_path(run).write_text(json.dumps(st, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---- 1-5: the context ---------------------------------------------------------------------------

def resolve(pr: str, repo_opt: Path | None, head_opt: str | None) -> dict:
    repo = repo_opt or repoinfo.repo_root(Path.cwd())
    if not repo:
        tm.fail("review: the cwd is not in a git repo. cd into a clone of the reviewed repo, or pass --repo", 2)
    url = repoinfo.origin_url(repo)
    slug = repoinfo.slug(url)
    name = repoinfo.repo_name(repo)
    cfg = config.load(name)
    run = config.runs_root() / name / str(pr)
    info = repoinfo.gh_pr(pr, slug, "headRefOid,baseRefName,headRefName,state,title")
    head = (info or {}).get("headRefOid")
    off: dict = {}
    base_name = (info or {}).get("baseRefName")
    if head_opt:
        if head and head != head_opt:
            print(f"review: --head {head_opt[:10]} overrides GitHub ({head[:10]})", file=sys.stderr)
        head = head_opt
    elif not head:
        head = offline.ls_remote_head(repo, str(pr))
    if not head:
        known = offline.last_known(run, repo)
        if not known:
            tm.fail(f"review: I can't reach GitHub and there is no earlier review of PR {pr}. "
                    "Run this where the network is available, or pass --head <sha>.", 2)
        head, base_name = known["head"], base_name or known["base"]
        off = {"offline": True, "offline_when": known["when"], "head_source": known["source"],
               "offline_reason": f"GitHub could not be reached (gh and git ls-remote both failed); the head is from {known['source']}"}
    base_name = base_name or "main"
    branch = cfg["ready_branch"].format(pr=pr)
    wt = repo / cfg["worktree_root"] / f"understando-{pr}-ready"
    return {"pr": str(pr), "repo": str(repo), "slug": slug or name, "name": name, "head": head, "base_name": base_name,
            "run": str(run), "branch": branch, "worktree": str(wt), "config": cfg.get("path"), "config_present": cfg["present"],
            "gh": bool(info), "state": (info or {}).get("state"), "head_branch": (info or {}).get("headRefName") or (load_state(run).get("head_branch")),
            "offline": bool(off), "offline_when": off.get("offline_when"), "offline_reason": off.get("offline_reason"), "head_source": off.get("head_source")}


def git_q(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def fetch(repo: Path, *refs: str) -> None:
    if repoinfo.origin_url(repo):
        git_q(repo, "fetch", "-q", "origin", *refs)


def setup_worktree(ctx: dict) -> dict:
    """Create the ready worktree, or pull it with --no-rebase. Never a rebase, never a force push."""
    repo, wt, branch, head = Path(ctx["repo"]), Path(ctx["worktree"]), ctx["branch"], ctx["head"]
    fetch(repo, f"+refs/heads/{branch}:refs/remotes/origin/{branch}")
    if repoinfo.rev(repo, head) is None:
        fetch(repo, head)
    remote = repoinfo.rev(repo, f"refs/remotes/origin/{branch}")
    local = repoinfo.rev(repo, f"refs/heads/{branch}")
    other = repoinfo.worktree_of(repo, branch)
    if other and other.resolve() != wt.resolve():
        wt = other
    if not wt.exists():
        wt.parent.mkdir(parents=True, exist_ok=True)
        if local:
            out = git_q(repo, "worktree", "add", "-q", str(wt), branch)
        elif remote:
            out = git_q(repo, "worktree", "add", "-q", "--track", "-b", branch, str(wt), f"origin/{branch}")
        else:
            out = git_q(repo, "worktree", "add", "-q", "-b", branch, str(wt), head)
        if out.returncode:
            tm.fail(f"review: cannot add the worktree {wt}: {out.stderr.strip()}", 1)
        made = "created"
    else:
        made = "present"
    pulled = None
    if remote:
        before = repoinfo.rev(wt, "HEAD")
        behind = int(git_q(wt, "rev-list", "--count", f"HEAD..origin/{branch}").stdout.strip() or 0)
        if behind:
            out = git_q(wt, *ident(wt), "-c", "pull.rebase=false", "pull", "-q", "--no-rebase", "--no-edit", "origin", branch)
            if out.returncode:
                tm.fail(f"review: `git pull --no-rebase` in {wt} failed. Resolve it by hand, then run review again:\n{out.stderr.strip()}", 1)
            pulled = {"commits": behind, "from": before, "to": repoinfo.rev(wt, "HEAD")}
    tip = repoinfo.rev(wt, "HEAD")
    return {"worktree": str(wt), "made": made, "pulled": pulled, "tip": tip,
            "ahead_of_head": int(git_q(repo, "rev-list", "--count", f"{head}..{tip}").stdout.strip() or 0),
            "pr_new": pr_new(wt, head, tip)}


def ident(wt: Path) -> list[str]:
    """The user's git identity when it is set; else the understando bot identity for a merge commit."""
    import ops
    if git_q(wt, "config", "user.email").stdout.strip():
        return []
    return list(ops.BOT)


def pr_new(wt: Path, head: str, tip: str | None) -> dict:
    """The PR commits that the ready branch does not have yet: {commits, subjects, shas, files}."""
    if not tip or repoinfo.rev(wt, head) is None:
        return {"commits": 0, "subjects": [], "shas": [], "files": []}
    log = git_q(wt, "log", "--reverse", "--format=%h %s", f"{tip}..{head}").stdout.splitlines()
    files = git_q(wt, "diff", "--name-only", f"{tip}...{head}").stdout.split()
    return {"commits": len(log), "subjects": [x.split(" ", 1)[1] if " " in x else "" for x in log],
            "shas": [x.split(" ", 1)[0] for x in log], "files": files}


def merge_head(st: dict) -> tuple[bool, str]:
    """Bring the PR head into the ready branch with a normal merge. Never a rebase, never a force push,
    never a push. A conflict aborts the merge and lists the files, so the worktree stays clean."""
    wt, head, branch = Path(st["worktree"]), st["head"], st["branch"]
    dirty = git_q(wt, "status", "--porcelain", "--untracked-files=no").stdout.strip()
    if dirty:
        return False, f"the review branch worktree has uncommitted changes ({len(dirty.splitlines())} files). Commit or stash them, then merge."
    out = git_q(wt, *ident(wt), "merge", "--no-ff", "--no-edit", "-m", f"Merge the PR head {head[:10]} into {branch}", head)
    if out.returncode:
        conflicts = git_q(wt, "diff", "--name-only", "--diff-filter=U").stdout.split()
        git_q(wt, "merge", "--abort")
        return False, ("the merge has conflicts in " + ", ".join(conflicts) + ". The merge is undone. Resolve it by hand "
                       f"(git -C {wt} merge {head[:10]}), then run review again.") if conflicts else f"git merge failed: {out.stderr.strip()}"
    return True, repoinfo.rev(wt, "HEAD") or ""


# ---- the guard ----------------------------------------------------------------------------------

def unpulled(st: dict) -> int:
    wt, branch = Path(st["worktree"]), st["branch"]
    if not wt.exists():
        return 0
    fetch(Path(st["repo"]), f"+refs/heads/{branch}:refs/remotes/origin/{branch}")
    if not repoinfo.rev(wt, f"refs/remotes/origin/{branch}"):
        return 0
    return int(git_q(wt, "rev-list", "--count", f"HEAD..origin/{branch}").stdout.strip() or 0)


def guard(run: Path, files: list[str], cfg: dict) -> list[str]:
    """The refusals for an edit of `files` on the ready branch now: a secret or protected path,
    commits on origin that the worktree has not pulled, or a live lock that covers the file."""
    out = []
    for f in files:
        r = config.refuse_edit(cfg, f)
        if r:
            out.append(r)
    st = load_state(run)
    if st.get("worktree"):
        n = unpulled(st)
        if n:
            out.append(f"refuse: {st['branch']} has {n} commits on origin that {st['worktree']} has not pulled. "
                       f"Run `understando review {st['pr']}` first: it pulls with --no-rebase.")
    for f in files:
        for h in lock.covering(run, f):
            out.append(f"refuse: {h['owner']} holds the run lock for `{h['verb']}` (pid {h['pid']}) on {', '.join(h['paths'])}, "
                       f"which covers {f}.")
    return out


# ---- the summary --------------------------------------------------------------------------------

def summary(c: context.Ctx, st: dict, sig: dict, doc: list[dict], prof: dict | None, cfg: dict) -> dict:
    data = c.data()
    out: dict = {"pr": st["pr"], "repo": st["slug"], "head": st["head"], "run": st["run"], "worktree": st["worktree"],
                 "branch": st["branch"], "ready_tip": st.get("tip"), "pulled": st.get("pulled"),
                 "ci": {"present": bool(prof), "approved": ci.approved(prof), "commands": len((prof or {}).get("commands", []))},
                 "doctor": {sev: [f["id"] for f in doc if f["severity"] == sev] for sev in ("auto", "mention", "route")},
                 "locks": lock.live(Path(st["run"])), "offline": bool(st.get("offline"))}
    if st.get("offline"):
        out["offline_reason"] = st.get("offline_reason")
        out["merge_question"] = "skipped (offline)"
    if not data:
        out["trust_map"] = None
        return out
    owners = cfg.get("deferred_owners") or {}
    out["verdicts"] = data.get("summary")
    out["open"] = [{"id": x["id"], "verdict": x["verdict"], "text": x["text"]} for x in data["claims"]
                   if x.get("verdict") in ("Gap", "Asserted") and not x.get("waiver")]
    out["deferred"] = [{"id": i["id"], "owner": i.get("owner") or owners.get(i["id"]) or "NO OWNER", "text": i.get("text", "")}
                       for i in data.get("invariants", []) if i.get("status") == "proposed" and (i.get("owner") or i.get("deferred") or owners.get(i["id"]))]
    out["formal_pending"] = [{"id": v["id"], "claims": v["claims"], "missing": v["formal_record"]["formal"].get("missing", [])}
                             for v in data["verifiers"]
                             if str(((v.get("formal_record") or {}).get("formal") or {}).get("verdict", "")).startswith("Formal (pending")]
    out["gates"] = sig.get("gates")
    out["reverify"] = sig.get("ready_branch", {}).get("reverify")
    return out


def summary_text(s: dict) -> str:
    lines = [f"review {s['repo']}#{s['pr']} at {s['head'][:10]}",
             f"  run folder: {s['run']}",
             f"  ready worktree: {s['worktree']} ({s['branch']} at {(s.get('ready_tip') or '')[:10]})"]
    if s.get("pulled"):
        lines.append(f"  pulled {s['pulled']['commits']} commits from origin with --no-rebase")
    if s.get("trust_map", 1) is None:
        lines.append("  no trust map yet: the map step writes it (commands/map.md)")
    else:
        lines.append("  verdicts: " + ", ".join(f"{k} {v}" for k, v in (s.get("verdicts") or {}).items()))
        lines += [f"  open {o['id']} {o['verdict']}: {o['text']}" for o in s.get("open", [])]
        lines += [f"  deferred {d['id']} (owner {d['owner']}): {d['text']}" for d in s.get("deferred", [])]
        lines += [f"  Formal (pending) {f['id']} ({', '.join(f['claims'])}): {'; '.join(f['missing'])}" for f in s.get("formal_pending", [])]
        rv = s.get("reverify") or {}
        if rv.get("claims"):
            lines.append(f"  re-verify on the ready branch: claims {', '.join(rv['claims'])}; verifiers {', '.join(rv['verifiers'])} "
                         f"({len(rv['changed'])} files changed after the map)")
        g = s.get("gates")
        lines.append("  gates: " + ("not computed" if not g else ("PASS" if g["pass"] else "FAIL") + (" (stale)" if g.get("stale") else "")
                                    + " " + " ".join(f"{k}={'pass' if v else 'fail'}" for k, v in g.items() if k.startswith("gate"))))
    lines.append(f"  CI profile: {s['ci']['commands']} commands, " + ("approved" if s["ci"]["approved"] else "NOT approved: show `understando ci` to the user"))
    lines.append("  doctor: " + "; ".join(f"{k} {len(v)}" for k, v in s["doctor"].items()))
    lines += [f"  lock: {h['owner']} {h['verb']} pid {h['pid']} on {', '.join(h['paths'])}" for h in s["locks"]]
    return "\n".join(lines)


# ---- the steps ----------------------------------------------------------------------------------

VERBOSE = [False]
SHOWN_FLAGS: set[str] = set()


def call(c: context.Ctx, verb: str, argv: list[str]) -> int:
    """Run a verb. Its full output goes to $R/logs/review-<verb>.log (with --verbose, to the screen);
    the screen gets the progress lines and each FLAG line in plain words."""
    import cli
    import names
    head = f"== review: {verb} {' '.join(argv)}".rstrip()
    if VERBOSE[0]:
        print("\n" + head)
        sys.stdout.flush()
        return cli.run_verb(verb, argv, c)
    logs = c.run / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / f"review-{verb}.log"
    sys.stdout.flush()
    sys.stderr.flush()
    saved = os.dup(1), os.dup(2)
    with open(log, "w", encoding="utf-8") as fh:
        fh.write(head + "\n")
        fh.flush()
        os.dup2(fh.fileno(), 1)
        os.dup2(fh.fileno(), 2)
        try:
            code = cli.run_verb(verb, argv, c)
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(saved[0], 1)
            os.dup2(saved[1], 2)
            os.close(saved[0])
            os.close(saved[1])
    data = c.data() or {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("FLAG ") and line not in SHOWN_FLAGS:
            SHOWN_FLAGS.add(line)
            print(names.plainify(line, data))
    if code:
        print(f"{verb}: the full output is in {log}")
    return code


def reverify_map(c: context.Ctx, st: dict) -> None:
    """Point the verifiers of the claims that the ready branch changed at the ready tip, so probe
    runs them at the fix. The map records the ready branch and its tip."""
    data = c.data()
    if not data or not st.get("tip") or st["tip"] == data["head"]:
        return
    import signals
    rv = signals.ready_changes(c, data, st["branch"], st["tip"])
    import cli
    cli.snapshot_before(c)
    data["ready"] = {"branch": st["branch"], "head": st["tip"]}
    moved = []
    for v in data["verifiers"]:
        if v["id"] in rv["verifiers"] and "command" in v and v.get("at") != st["tip"]:
            v["at"] = st["tip"]
            moved.append(v["id"])
    tm.save(data, c.map)
    if moved and VERBOSE[0]:
        print(f"review: {', '.join(moved)} run at the ready tip {st['tip'][:10]}: the ready branch changed their code or tests")


def formal_step(c: context.Ctx, st: dict) -> int:
    """Run the approved formal commands of ci.json in a scratch checkout of the ready tip."""
    prof = ci.load(c.run) or {}
    cmds = [x for x in prof.get("commands", []) if x.get("kind") == "formal"]
    if not cmds:
        print("review: formal: no formal check in the CI profile; skip")
        return 0
    if not ci.approved(prof):
        print("refuse: the CI profile is not approved")
        return 1
    ok = {x["id"] for x in ci.approved_commands(prof)}
    for x in [x for x in cmds if x["id"] not in ok]:
        print(f"  {x['id']} skip: the user did not approve it (the approval covers only {', '.join(prof['approval'].get('projects') or [])})")
    cmds = [x for x in cmds if x["id"] in ok]
    results = []
    with tempfile.TemporaryDirectory(prefix="understando-formal-") as tmp:
        root = Path(tmp)
        for d in sorted({x["cwd"] for x in cmds}):
            ci.extract(Path(st["repo"]), st["tip"], d, root)
        for x in cmds:
            out = subprocess.run(x["argv"], cwd=root / x["cwd"], capture_output=True, text=True, timeout=1800)
            status = "green" if out.returncode == 0 else ("red" if out.returncode == 1 else "error")
            results.append({"id": x["id"], "argv": x["argv"], "status": status, "exit": out.returncode})
            print(f"  {x['id']} {status}: {' '.join(a if '/' not in a else Path(a).name for a in x['argv'])}")
    results += replay_step(c, st, prof)
    (c.run / "formal-recheck.json").write_text(json.dumps({"tip": st["tip"], "at": tm.now(), "results": results}, indent=2) + "\n")
    side = c.run / "formal" / "verifiers.json"
    if side.is_file():
        print(f"review: formal: re-run the frog scripts of {c.run / 'formal'} at the ready tip, re-stamp each record "
              f"(formal_record.py stamp), then run `understando formalize --sidecar {side}`. The user starts formalize.")
    return 0 if all(r["status"] == "green" for r in results) else 1


def replay_step(c: context.Ctx, st: dict, prof: dict) -> list[dict]:
    """The conformance run (the trace replay) of each formal verifier whose code or model the ready
    branch changed, at the ready tip, in a scratch worktree. Only a command that the approved CI
    profile allows runs; it takes the cwd of a verifier that runs the same tool."""
    import shlex
    import ops
    import run_control
    import signals
    data = c.data() or {}
    rv = signals.ready_changes(c, data, st["branch"], st.get("tip")) if data else {"verifiers": []}
    allowed = {"commands": ci.approved_commands(prof)}
    runs = []
    for v in data.get("verifiers", []):
        src = ((v.get("formal") or {}).get("conformance") or {}).get("source", "")
        if (tm.ladder(v) or 0) < 4 or v["id"] not in rv["verifiers"] or not src:
            continue
        argv = shlex.split(src)
        sib = next((x for x in data["verifiers"] if "command" in x and x["command"]["argv"][:4] == argv[:4]), None)
        cwd = (sib or {}).get("command", {}).get("cwd", ".")
        if not ci.allowed_by(allowed, argv, cwd):
            print(f"  {v['id']} replay skip: `{src}` is not in the approved CI profile")
            continue
        runs.append({"id": f"{v['id']}-replay", "kind": "integration", "claims": v["claims"], "command": {"argv": argv, "cwd": cwd, "timeout_s": 1800}})
    if not runs:
        return []
    tmp = {"head": st["tip"], "verifiers": runs, "controls": [], "setup": data.get("setup", [])}
    with ops.scratch_clone(Path(st["repo"])) as (clone, wt):
        run_control.run_baseline(tmp, clone, wt, None, {r["id"] for r in runs})
    out = []
    for r in runs:
        b = r.get("baseline") or {}
        out.append({"id": r["id"], "argv": r["command"]["argv"], "status": b.get("status", "error"), "exit": b.get("exit")})
        print(f"  {r['id']} {b.get('status', 'error')}: the trace replay at the ready tip")
    return out


def probe_done_outside(c: context.Ctx, st: dict, scope: list[str] | None) -> bool:
    """True when each verifier in scope (and each of its controls) already ran at its commit after
    this review started: a manual `understando probe` of the same scope counts as the probe step."""
    data = c.data()
    if not data or not scope or not st.get("started_at"):
        return False
    import run_control
    for v in data["verifiers"]:
        if v["id"] not in scope:
            continue
        b = v.get("baseline") or {}
        if b.get("head") != run_control.commit_of(v, data) or (b.get("ran_at") or "") < st["started_at"]:
            return False
        for k in data["controls"]:
            if k["verifier"] == v["id"] and ((k.get("result") or {}).get("ran_at") or "") < st["started_at"]:
                return False
    return True


def run_step(c: context.Ctx, st: dict, step: str, answers: dict) -> tuple[int, str | None]:
    """(exit, stop reason). A stop reason ends the run, also under "run through". A long step prints
    a heartbeat line every 30 seconds ($UNDERSTANDO_HEARTBEAT changes the interval)."""
    import heartbeat
    with heartbeat.beat(f"review {step}"):
        return _run_step(c, st, step, answers)


def _run_step(c: context.Ctx, st: dict, step: str, answers: dict) -> tuple[int, str | None]:
    if step in ("close", "trim", "formal"):
        n = unpulled(st)
        if n:
            return 1, f"{st['branch']} has {n} commits on origin that the worktree has not pulled. Run `understando review {st['pr']}` again."
    if step == "map":
        if not c.data():
            return 1, "No trust map yet. Write the claim ledger (commands/map.md), then run review again."
        reverify_map(c, st)
        return call(c, "map", []), None
    if step == "probe":
        scope = probe_scope(c, st)
        if scope == []:
            print("\n== review: probe: no verifier changed on the ready branch, and each one has a control result; skip")
            return 0, None
        if probe_done_outside(c, st, scope):
            print(f"\n== review: probe: each of the {len(scope)} verifiers in scope already ran at its commit after this review started; done")
            return 0, None
        extra = (["--only", ",".join(scope)] if scope else []) + (["--paid", ",".join(answers["paid"])] if answers.get("paid") else [])
        return call(c, "probe", extra), None
    if step == "formal":
        import signals
        data = c.data() or {}
        rv = signals.ready_changes(c, data, st["branch"], st.get("tip")) if data else {"verifiers": []}
        formal_ids = {v["id"] for v in data.get("verifiers", []) if (tm.ladder(v) or 0) >= 4}
        if not (formal_ids & set(rv["verifiers"])) and not any(x.get("kind") == "formal" for x in (ci.load(c.run) or {}).get("commands", [])):
            print("\n== review: formal: nothing to check again; skip")
            return 0, None
        print("\n== review: formal")
        return formal_step(c, st), None
    if step == "close":
        if answers.get("close"):
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=c.run) as fh:
                json.dump(answers["close"], fh)
            try:
                code = call(c, "close", ["--answers", fh.name])
            finally:
                os.unlink(fh.name)
            answers.pop("close")
            if code:
                return code, None
            data = c.data() or {}
            return 0, ("close" if any(x.get("verdict") not in CLOSED and not x.get("waiver") for x in data.get("claims", [])) else None)
        data = c.data() or {}
        if any(x.get("verdict") not in CLOSED and not x.get("waiver") for x in data.get("claims", [])):
            return 0, "close"
        return 0, None
    if step == "trim":
        return call(c, "trim", []), None
    if step == "ready":
        return call(c, "ready", ["--report"]), None
    if step == "explain":
        code = call(c, "explain", [])
        sec = c.run / "pr-section.md"
        if sec.is_file():
            print(f"\n== review: pr-section.md ({sec}). Paste it into the PR body yourself; understando never edits the PR.\n")
            print(sec.read_text(encoding="utf-8"))
        return code, None
    tm.fail(f"review: unknown step {step}", 2)
    return 2, None


# ---- the prompt ---------------------------------------------------------------------------------

def stage_of(step: str) -> str:
    return next(name for name, steps in STAGES if step in steps)


def next_stage(done: list[str]) -> str | None:
    return next((name for name, steps in STAGES if any(x not in done for x in steps)), None)


def probe_scope(c: context.Ctx, st: dict) -> list[str] | None:
    """The verifiers that probe runs in the check stop: None for all (no probe ran yet), else the
    verifiers that the ready branch changed, the verifiers of a possible bug whose code changed, and
    the verifiers with no control result. An empty list: nothing to probe."""
    import signals
    data = c.data()
    if not data:
        return None
    sig = signals.collect(c, st.get("head"))
    if not sig.get("last_probe"):
        return None
    rv = ((sig.get("ready_branch") or {}).get("reverify") or {})
    bug_claims = {x for b in sig["discover"].get("bug_changes", []) if b["changed"] for x in b["claims"]}
    ids = set(rv.get("verifiers") or []) | set(sig.get("untested_verifiers") or [])
    ids |= {v["id"] for v in data["verifiers"] if set(v.get("claims", [])) & bug_claims}
    return sorted(i for i in ids if any(v["id"] == i and "command" in v for v in data["verifiers"]))


def recorded_seconds(data: dict, vids: set[str] | None) -> tuple[float, int]:
    """The recorded run time of the verifiers and their controls: (seconds, how many runs were recorded)."""
    total, n = 0.0, 0
    for v in data["verifiers"]:
        if "command" not in v or (vids is not None and v["id"] not in vids):
            continue
        sec = (v.get("baseline") or {}).get("seconds") or (v.get("cost") or {}).get("seconds")
        if sec:
            total, n = total + float(sec), n + 1
        for k in data["controls"]:
            if k.get("verifier") == v["id"]:
                ks = (k.get("result") or {}).get("seconds") or sec
                if ks:
                    total, n = total + float(ks), n + 1
    return total, n


def paid_in(c: context.Ctx, data: dict, vids: set[str] | None, paid: list[str]) -> list[dict]:
    cfg = config.load(repoinfo.repo_name(c.repo)) if c.repo else {}
    return [v for v in data["verifiers"] if "command" in v and (vids is None or v["id"] in vids) and v["id"] not in paid
            and config.needs_key(cfg, v["command"]["argv"])]




# ---- plain words --------------------------------------------------------------------------------
# The prompt shows plain names (scripts/names.py). IDs, SHAs and paths go in `details` (--verbose),
# in a trailing "(ref: ...)" part, or in the JSON fields.

VERDICT_WORDS = [("Formal", "proven formally"), ("Proven", "proven by tests"), ("Backed", "backed but not proven"),
                 ("Asserted", "only stated"), ("Gap", "not checked")]


def merge_state(c: context.Ctx, data: dict) -> tuple[str, list[dict]]:
    """The merge verdict of the explainer (scripts/derive.py merge_verdict), so the blocker count is the same."""
    import derive
    rp = c.run / "ready.json"
    ready = tm.load(rp) if rp.is_file() else None
    if ready and ready.get("head") != data.get("head"):
        ready = None
    cfg = {}
    if c.repo:
        import config
        import repoinfo
        try:
            cfg = config.load(repoinfo.repo_name(c.repo))
        except Exception:  # noqa: BLE001  the default bars
            cfg = {}
    return derive.merge_verdict(data, ready, derive.risky_unclaimed(c.run, data), cfg)


def standing(c: context.Ctx, data: dict) -> str:
    import prompt
    summ = data.get("summary") or {}
    counts = ", ".join(f"{summ[k]} {w}" for k, w in VERDICT_WORDS if summ.get(k))
    form, items = merge_state(c, data)
    verdict = {"not-ready": f"Not ready: {prompt.n_of(len(items), 'blocker')}.",
               "accept": f"Ready if you accept {prompt.n_of(len(items), 'risk')}.", "ready": "Ready to merge."}[form]
    return f"Now: {counts}. {verdict}"


def bug_name(data: dict, inv_id: str) -> str:
    import names
    return names.of(data, inv_id)


def explainer_line(row: dict | None) -> str | None:
    if not row:
        return None
    if not row["present"]:
        return None
    stale = f" It is out of date ({row['stale_why']})." if row.get("stale") else ""
    start = "start with 'Can you merge it?'" if row["anchor"] == "merge" else f"see {row['section']}"
    if row["opened"]:
        return f"I opened the explainer: {start}.{stale}"
    return f"The explainer is ready: {start} (ref: {row['url']}).{stale}"


def drift_line(doc: list[dict]) -> str | None:
    import prompt
    anchors = [f for f in doc if f["id"].startswith("anchor-drift")]
    formal = [f for f in doc if f["id"] == "formal-drift"]
    parts = []
    if anchors:
        import re
        n = max([int(m) for f in anchors for m in re.findall(r"(\d+) code (?:anchors?|refs?)", f.get("summary", ""))] or [len(anchors)])
        parts.append(f"{prompt.n_of(n, 'code excerpt')} point at code that moved; map will re-point them")
    if formal:
        parts.append(f"{prompt.n_of(len(formal), 'formal model')} {'is' if len(formal) == 1 else 'are'} older than the code {'it covers' if len(formal) == 1 else 'they cover'}; the re-check runs {'it' if len(formal) == 1 else 'them'} again")
    return ("; ".join(parts) + ".")[:1].upper() + ("; ".join(parts) + ".")[1:] if parts else None


def rechecked(data: dict, rv: dict, tip: str | None) -> bool:
    """True when each changed verifier with a command already ran at the ready tip."""
    vs = [v for v in data.get("verifiers", []) if v["id"] in (rv.get("verifiers") or []) and "command" in v]
    return bool(vs) and all((v.get("baseline") or {}).get("head") == tip for v in vs)


def situation(c: context.Ctx, s: dict, st: dict, sig: dict, doc: list[dict]) -> tuple[list[str], list[str]]:
    """At most five plain lines, and the details (IDs, SHAs, paths) for --verbose."""
    import names
    import prompt
    lines, details = [], []
    if st.get("offline"):
        lines.append(f"I can't reach GitHub, so I can't see new PR commits. I'm using the last known PR head (from {st.get('offline_when')}).")
        details.append(f"offline: {st.get('offline_reason')}; head {st['head'][:10]}; the merge question was skipped; publish is refused")
    data = c.data() or {}
    new = st.get("pr_new") or {}
    merged = (st.get("merge") or {}).get("head") == st["head"]
    if new.get("commits") and not merged:
        lines.append(f"Your PR has {prompt.n_of(new['commits'], 'new commit')} that the review branch does not have yet.")
        details.append(f"PR head {st['head'][:10]}; new commits: {', '.join(new['shas'][:6])}")
    tmap = sig.get("trust_map") or {}
    rb = sig.get("ready_branch") or {}
    rv = rb.get("reverify") or {}
    bugs = [b for b in sig.get("discover", {}).get("bug_changes", []) if b["changed"]]
    also = "also " if lines else ""
    if bugs:
        b = bugs[0]
        more = f" and {len(bugs) - 1} more" if len(bugs) > 1 else ""
        lines.append(f"The review branch {also}has a fix for the possible bug '{bug_name(data, b['invariant'])}'{more}, which is not checked yet.")
        details.append(f"possible bug {b['invariant']}: {', '.join(b['where'])}" + (f" changed in {', '.join(b['commits'])}" if b["commits"] else ""))
    elif rv.get("claims") and not rechecked(data, rv, st.get("tip")):
        lines.append(f"The review branch {also}changed the code or checks of {names.listing([names.of(data, x) for x in rv['claims']])}, which are not checked again yet.")
    if st.get("tip") and st["tip"] != st["head"]:
        details.append(f"{st['branch']} at {st['tip'][:10]}; the map is at {(tmap.get('head') or '')[:10]}")
    if data.get("claims"):
        import onto
        unsure = [x for x in data["claims"] if onto.surface(data, x) == "unsure"]
        if unsure:
            lines.append(f"I am not sure of the surface of {names.listing([names.of(data, x['id']) for x in unsure])}: frontend, backend, LLM or other? "
                         "Tell me, and I set it (understando map --surface).")
            details.append("unsure surface: " + ", ".join(x["id"] for x in unsure))
        below = [x for x in data["claims"] if not x.get("waiver") and onto.risky(x) and not onto.bar(data, x)["met"]]
        if below:
            lines.append(f"{prompt.n_of(len(below), 'risky claim')} {'is' if len(below) == 1 else 'are'} below {'its' if len(below) == 1 else 'their'} bar: "
                         f"{names.listing([names.of(data, x['id']) for x in below])}.")
            details.append("below the bar: " + "; ".join(f"{x['id']} {onto.bar(data, x)['text']}" for x in below[:6]))
    if s.get("trust_map", 1) is None:
        lines.append("No trust map yet: the first step writes it.")
    else:
        lines.append(standing(c, data))
        details.append("verdicts: " + ", ".join(f"{k} {v}" for k, v in (s.get("verdicts") or {}).items())
                       + "; open: " + ", ".join(o["id"] for o in s.get("open") or []))
    row = st.get("opened")
    if row:
        import opener
        page = opener.status(c.run, data)
        row = {**row, "present": page["present"], "stale": page["stale"], "stale_why": page["why"] if page["stale"] else None}
    ex = explainer_line(row)
    if ex:
        lines.append(ex)
    if s["ci"]["present"] and not s["ci"]["approved"]:
        prof = ci.load(Path(st["run"])) or {}
        lines.append(f"CI: {prompt.n_of(s['ci']['commands'], 'command')} from your workflows, because {ci.why_line(prof)}; not approved yet." if prof
                     else "CI: no profile yet.")
    if s["locks"]:
        h = s["locks"][0]
        lines.append(f"Another agent ({h['owner']}) is writing with {h['verb']} now.")
        details.append(f"lock: {h['owner']} {h['verb']} pid {h['pid']} on {', '.join(h['paths'])}")
    d = drift_line(doc)
    if d:
        lines.append(d)
        details += [f"doctor {f['id']}: {f['summary']}" for f in doc if f["id"].startswith(("anchor-drift", "formal-drift"))]
    return lines[:5], details


def next_info(c: context.Ctx, st: dict, stage: str, answers: dict) -> tuple[dict, list[str]]:
    """The Next line (plain), and its IDs for the details."""
    import prompt
    import signals
    data = c.data() or {}
    timings = st.get("timings") or {}

    def took(*steps: str) -> str | None:
        rec = [timings[x] for x in steps if x in timings]
        return (prompt.human_seconds(sum(rec)) + " (the last recorded run)") if rec else None

    if stage == "check":
        if not data:
            return ({"step": "map", "does": "Write the claim ledger, then map", "scope": "every claim",
                     "cost": "$0, no model call by the CLI", "time": "unknown: no recorded run", "writes": "the trust map in the run folder"}, [])
        scope = probe_scope(c, st)
        vids = None if scope is None else set(scope)
        sig = signals.collect(c, st.get("head"))
        bugs = [b for b in sig["discover"].get("bug_changes", []) if b["changed"]]
        rv = (sig.get("ready_branch") or {}).get("reverify") or {}
        claims = sorted({x for b in bugs for x in b["claims"]} | set(rv.get("claims") or []), key=lambda x: (len(x), x))
        sec, n = recorded_seconds(data, vids)
        sec += timings.get("map", 5)
        keyed = paid_in(c, data, vids, answers.get("paid") or [])
        formal = [v["id"] for v in data["verifiers"] if (tm.ladder(v) or 0) >= 4 and v["id"] in (rv.get("verifiers") or [])]
        what = ("Re-check the fix for '" + bug_name(data, bugs[0]["invariant"]) + "' and the code it changed" if bugs
                else "Re-check the changed code" if scope else "Map, then probe every test with its planted bug")
        n_tests = len(scope) if scope is not None else sum(1 for v in data["verifiers"] if "command" in v)
        scope_txt = "every claim" if scope is None else \
            ", ".join(x for x in [prompt.n_of(len(claims), "claim") if claims else "", prompt.n_of(n_tests, "test"),
                                  prompt.n_of(len(formal), "formal model") if formal else ""] if x)
        usd = sum(float((v.get("cost") or {}).get("usd") or 0) for v in keyed)
        calls = sum(int((v.get("cost") or {}).get("model_calls") or 1) for v in keyed)
        info = {"step": "check", "does": what, "scope": scope_txt,
                "cost": "$0, no model call" if not keyed else f"$0; {prompt.n_of(len(keyed), 'paid check')} (about ${usd:.2f}, {calls} model calls) wait for your yes",
                "time": (prompt.human_seconds(sec) + f" (from {n} recorded runs)") if n else (took("map", "probe") or "unknown: no recorded run"),
                "writes": "the trust map and its history in the run folder; no commit"}
        return info, [f"claims: {', '.join(claims)}" if claims else "", f"verifiers: {', '.join(scope or [])}" if scope else "",
                      f"formal: {', '.join(formal)}" if formal else "", f"paid: {', '.join(v['id'] for v in keyed)}" if keyed else ""]
    if stage == "trim":
        n = sum(1 for v in data.get("verifiers", []) if "unit" in str(v.get("kind", "")))
        return ({"step": "trim", "does": "Find excess code, and delete each unit test that an end-to-end test already covers",
                 "scope": f"{prompt.n_of(n, 'unit test')} and the changed code", "cost": "$0, no model call",
                 "time": took("trim") or "unknown: no recorded run", "writes": "trim.json; each deletion is a commit on the review branch"}, [])
    if stage == "ship":
        return ({"step": "ship", "does": "Compute the four gates, then build the explainer and the PR section",
                 "scope": "the whole trust map", "cost": "$0, no model call", "time": took("ready", "explain") or "unknown: no recorded run",
                 "writes": "ready.json, the explainer and pr-section.md in the run folder; nothing edits the PR"}, [])
    return ({"step": "close", "does": "One question for each open claim", "scope": "the open claims, riskiest first", "cost": "$0",
             "time": "a few minutes for each claim", "writes": "the trust map; a new test is a commit on the review branch"}, [])


def link_proposals(c: context.Ctx, st: dict) -> list[dict]:
    """The new tests on the ready branch that wait for the user's link decision."""
    import newtests
    data = c.data()
    if not data or not st.get("tip"):
        return []
    decided = st.get("links") or {}
    return [p for p in newtests.proposals(c, data, st["tip"]) if p["test"] not in decided and p["claim"] and p["argv"]]


def merge_question(c: context.Ctx, st: dict, sit: list[str], details: list[str]) -> dict:
    import prompt
    new = st["pr_new"]
    n = new["commits"]
    data = c.data() or {}
    sig_bugs = [b for b in __import__("signals").bug_changes(c, data, st.get("tip")) if b["changed"]] if data else []
    only = f"the fix for '{bug_name(data, sig_bugs[0]['invariant'])}'" if sig_bugs else "the existing items"
    word = prompt.n_of(n, "new commit") if n > 1 else "the new commit"
    return prompt.make(sit, f"Bring {word} into the review branch? (a merge, no force-push)", [
        prompt.option(f"Merge, then re-check everything {'it touches' if n == 1 else 'they touch'}",
                      f"Merges the PR head into the review branch: a normal merge, no rebase, no force-push, no push. A conflict stops the merge and lists the files. Then the re-check covers the code that {'it changes' if n == 1 else 'they change'}.",
                      f"understando review {st['pr']} --merge"),
        prompt.option(f"Show what {'the commit changes' if n == 1 else f'the {n} commits change'} first",
                      "Lists each new commit and the files that it changes. Nothing changes.", f"understando review {st['pr']} --show-new"),
        prompt.option(f"Skip; re-check only {only}", "Keeps the review branch as it is. The re-check uses the code that it has now.",
                      f"understando review {st['pr']} --skip-merge")],
        {"step": "merge", "does": "Merge the new PR commits into the review branch",
         "scope": f"{prompt.n_of(n, 'commit')}, {prompt.n_of(len(new['files']), 'file')}", "cost": "$0, no model call",
         "time": "a few seconds", "writes": "one merge commit on the review branch; no push"}, details=details + [f"new: {x}" for x in new["shas"]])


def link_question(c: context.Ctx, st: dict, p: dict, sit: list[str], details: list[str], left: int) -> dict:
    import names
    import prompt
    data = c.data() or {}
    claim = names.of(data, p["claim"])
    words = " ".join(p["words"].split()[:9])
    return prompt.make(sit[:4] + [f"The review branch adds a test that {words}. It most likely checks '{claim}'."
                                  + (f" {prompt.n_of(left - 1, 'other new test')} wait." if left > 1 else "")],
                       f"Link the new test to '{claim}'?", [
        prompt.option("Link it, then probe it", f"Adds the test as a check of '{claim}', with one planted bug: the code as it was before the fix. "
                      "The claim moves only after probe shows the test goes red on that bug.",
                      f"understando review {st['pr']} --link yes"),
        prompt.option("Do not link it", "Keeps the test out of the trust map. The claim keeps its old evidence.", f"understando review {st['pr']} --link no")],
        {"step": "link", "does": "Link the new test to its claim", "scope": "one test", "cost": "$0, no model call", "time": "about 1 s",
         "writes": "the trust map; no commit"},
        else_does="Name another claim for it, or tell me what to do instead. Nothing runs until you say.",
        details=details + [f"test {p['test']} in {p['file']}; claim {p['claim']} (score {p['score']}); command {' '.join(p['argv'])}"]) | {"test": p["test"]}


def teach_question(c: context.Ctx, st: dict, sit: list[str], details: list[str], nxt_stage: str | None) -> dict:
    import opener
    import prompt
    pr = st["pr"]
    page = opener.status(c.run, c.data())
    opts = []
    if not page["present"]:
        opts.append(prompt.option("Build the explainer first", "Builds the explainer page (about a minute), so the walk-through can open each part of it.",
                                  f"understando explain --html; then understando review {pr} --teach"))
    elif page["stale"]:
        opts.append(prompt.option("Rebuild the explainer first", f"The page is out of date ({page['why']}). Builds it again, then walks through it.",
                                  f"understando explain --html; then understando review {pr} --teach"))
    opts.append(prompt.option("Walk me through the change", "Opens the explainer one part at a time: the story, the loop, what changed, the weakest promises. "
                              "In chat: at most four ideas, the code by refs, and your questions.", f"understando review {pr} --teach"))
    opts.append(prompt.option(f"Go on to {STAGE_NAME.get(nxt_stage or 'close', 'close')}", "Skips the walk-through. You can ask for it later.",
                              f"understando review {pr} --skip-teach"))
    return prompt.make(sit, "Walk through the change before the next stop?", opts,
                       {"step": "teach", "does": "Walk through the change with the explainer", "scope": "two to four ideas, weakest promise first",
                        "cost": "$0, no model call", "time": "a few minutes, at your pace", "writes": "nothing"}, details=details)


def build_prompt(c: context.Ctx, st: dict, s: dict, sig: dict, answers: dict, doc: list[dict] | None = None) -> dict:
    import close
    import prompt
    pr = st["pr"]
    stage = next_stage(st.get("done", []))
    sit, details = situation(c, s, st, sig, doc or [])
    prof = ci.load(c.run)
    if st.get("failed"):
        f = st["failed"]
        return prompt.make(sit[:4] + [f"The last {f['step']} step stopped: {f['plain']}"], f"Retry the {f['step']} step?", [
            prompt.option(f"Retry {f['step']}", "Runs the step again from the start.", f"understando review {pr} --go"),
            prompt.option(f"Skip {f['step']}", "Marks the step as skipped and goes on. The report says that it was skipped.",
                          f"understando review {pr} --skip {f['step']}")],
            {"step": f["step"], "does": f"Run {f['step']} again", "scope": "the same scope", "cost": "$0, no model call",
             "time": "as before", "writes": "the same files as before"}, details=details + [f"failed: {f['reason']}"])
    new = st.get("pr_new") or {}
    if new.get("commits") and (st.get("merge") or {}).get("head") != st["head"]:
        return merge_question(c, st, sit, details)
    if stage is None:
        sec = c.run / "pr-section.md"
        teach = [] if (st.get("teach") or {}).get("turn") else [
            prompt.option("Walk me through the change", "Opens the explainer one part at a time, with at most four ideas and the code by refs.",
                          f"understando review {pr} --teach")]
        return prompt.make(sit, "The review is complete. What next?",
                           teach + [prompt.option("Show the PR section", "Prints the text for you to paste into the PR body. understando never edits the PR.",
                                          f"cat {sec}"),
                            prompt.option("Review again", "Resolves the PR again, pulls the review branch, and asks the next question.",
                                          f"understando review {pr}")], details=details)
    nxt, more = next_info(c, st, stage, answers)
    details = details + [m for m in more if m]
    if stage != "close" and not ci.approved(prof) and prof:
        q = ci.question(prof, then=f"review runs {STAGE_NAME[stage]}")
        for o in q["options"]:
            if o.get("run", "").startswith("understando ci --approve"):
                o["run"] += f"; then understando review {pr} --go"
        q["situation"] = [x for x in sit if not x.startswith("CI:")][:4] + q["situation"]
        q["next"] = nxt
        q["details"] = details
        prompt.check(q)
        return q
    if stage == "check":
        props = link_proposals(c, st)
        if props:
            return link_question(c, st, props[0], sit, details, len(props))
    if stage != "check" and "map" in st.get("done", []) and not st.get("teach") and not st.get("through"):
        return teach_question(c, st, sit, details, stage)
    if stage == "close":
        data = c.data() or {}
        q = close.question(data, pr)
        if q:
            for o in q["options"]:
                if o.get("choice"):
                    o["run"] = f"understando review {pr} --go --answers <file with {{\"close\": {{\"answers\": [{{\"claim\": \"{q['claim']}\", \"choice\": \"{o['choice']}\", ...}}]}}}}>"
            q["situation"] = [x for x in sit if x.startswith("Now:")][:1] + q["situation"]
            q["details"] = details + q.get("details", [])
            prompt.check(q)
            return q
    opts = [prompt.option(f"Run {STAGE_NAME[stage]}", nxt["does"] + ".", f"understando review {pr} --go")]
    if stage == "check":
        import opener
        page = opener.status(c.run, c.data())
        if page["present"] and page["stale"]:
            opts.append(prompt.option("Rebuild the explainer first", f"The page is out of date ({page['why']}). Builds it again; nothing else runs.",
                                      "understando explain --html"))
        keyed = paid_in(c, c.data() or {}, None if probe_scope(c, st) is None else set(probe_scope(c, st) or []),
                        answers.get("paid") or []) if c.data() else []
        if keyed:
            ids = [v["id"] for v in keyed]
            usd = sum(float((v.get("cost") or {}).get("usd") or 0) for v in keyed)
            opts.append(prompt.option(f"Also run the {prompt.n_of(len(keyed), 'paid check')} (about ${usd:.2f})",
                                      "Runs them with the model key from the key file, after this yes only.",
                                      f"understando review {pr} --go --answers <file with {{\"paid\": {json.dumps(ids)}}}>"))
    opts.append(prompt.option("Run through", "Runs every stop that needs no decision. It still stops for each open claim, the CI approval "
                              "and each paid step.", f"understando review {pr} --through"))
    return prompt.make(sit, f"Run {STAGE_NAME[stage]}?", opts, nxt, details=details)


# ---- teach ----------------------------------------------------------------------------------------

TEACH_LEVELS = [("story", "story"), ("loop", "loop"), ("change", "changed"), ("promises", None)]


def teach_turn(c: context.Ctx, st: dict, no_open: bool, page_dir: Path | None = None, data: dict | None = None) -> str:
    """One teach turn: open the next part of the explainer, add only what the page cannot (the two to
    four ideas that matter, with code refs and the check behind each "this is guaranteed"), and end
    with one question. references/adapted/teach.md holds the rules."""
    import derive
    import names
    import opener
    data = data or c.data() or {}
    page_dir = page_dir or c.run
    t = st.get("teach") or {"turn": 0}
    st["teach"] = t
    i = t.get("turn", 0)
    if i >= len(TEACH_LEVELS):
        return "The walk-through is done. Ask about any part, or go on to the next stop."
    level, anchor = TEACH_LEVELS[i]
    order = derive.promises_in_order(data) if data.get("promises") else []
    if anchor is None and order:
        anchor = f"promise-{opener.slug(order[0][0]['id'])}"
    row = opener.open_page(page_dir, data, level=None if anchor else level, anchor=anchor or level, no_open=no_open, why="teach", log_dir=c.run)
    st.setdefault("opened_log", []).append(row)
    t["turn"] = i + 1
    t["opened"] = row["anchor"]
    if row["present"]:
        lead = (f"I opened {row['section']}." if row["opened"] else f"Open {row['section']} (ref: {row['url']}).") \
            + (f" The page is out of date ({row['stale_why']})." if row.get("stale") else "")
    else:
        lead = "There is no explainer page yet, so I tell it here."
    claims = {x["id"]: x for x in data.get("claims", [])}
    vers = data.get("verifiers", [])
    out = [lead]
    if i == 0:
        picks = order[:4]
        out.append(f"{len(picks)} ideas matter most in this PR; the rest can wait." if picks else "The map has no promises yet.")
        for n, (p, strength, cids) in enumerate(picks, 1):
            weak = claims[cids[0]]
            ver = next((v for v in vers if weak["id"] in v["claims"] and v.get("state") == "proven"), None) \
                or next((v for v in vers if weak["id"] in v["claims"]), None)
            code = (weak.get("code") or [{}])[0]
            ref = ", ".join(x for x in [p["id"], weak["id"], ver["id"] if ver else "",
                                        f"code: understando snippet {code['path']}::{code['symbol']}" if code.get("symbol") else ""] if x)
            word = dict(VERDICT_WORDS).get(weak.get("verdict"), "not rated")
            if weak.get("verdict") in ("Formal", "Proven") and ver:
                fact = f"guaranteed, because {ver.get('name') or names.verifier_name(ver, claims)} catches a planted bug"
            elif weak.get("verdict") == "Backed":
                fact = "backed, but no planted bug proves that the check can fail"
            else:
                fact = "unknown: no check shows it"
            out.append(f"  {n}. {p.get('label') or p['id']}: its weakest part is '{names.of(data, weak['id'])}' ({word}; {fact}). (ref: {ref})")
        out.append("Which idea do you want to trace in the code first? Or say 'next', and I open the loop.")
    elif level == "loop":
        out.append("The loop shows one run from start to end: who acts, what it calls, and what state changes. Ask about any step, and I trace it in the code.")
        out.append("Which step is not clear? Or say 'next' for what changed.")
    elif level == "change":
        out.append("This part shows the existing code, the new code and what replaced what. The unclaimed changes below it are code that no claim covers.")
        out.append("Which change do you want to see in the code? Or say 'next' for the weakest promise.")
    else:
        p = order[0][0] if order else None
        out.append(f"This is the weakest promise{': ' + (p.get('label') or '') if p else ''}. Its claims show what is proven, what is only backed, and what is unknown.")
        out.append("Can you say in one sentence why this promise is weak? Then we go on to close it.")
    return "\n".join(out)


# ---- stop reports -------------------------------------------------------------------------------

def verdict_of(data: dict | None) -> dict[str, str]:
    return {x["id"]: x.get("verdict") for x in (data or {}).get("claims", [])}


def stop_report(c: context.Ctx, st: dict, before: dict[str, str], ran: list[str], scope: list[str] | None, no_open: bool) -> list[str]:
    """What was checked, what passed, and what changed for the reviewer, in plain words."""
    import names
    import opener
    import prompt
    data = c.data() or {}
    rank = {k: i for i, (k, _) in enumerate(VERDICT_WORDS)}
    out = []
    vs = [v for v in data.get("verifiers", []) if "command" in v and (scope is None or v["id"] in scope)]
    if "probe" in ran and vs:
        caught = [v for v in vs if v.get("state") == "proven"]
        n_claims = len({c for v in vs for c in v.get("claims", [])})
        out.append(f"Checked: {prompt.n_of(len(vs), 'check')} of {prompt.n_of(n_claims, 'claim')}, each with its planted bug. "
                   f"Passed: {len(caught)} of {len(vs)} caught their planted bug." + names.ref([v["id"] for v in vs]))
        dead = [v for v in vs if v.get("state") in ("cannot-fail", "failing", "broken")]
        if dead:
            out.append(f"Look at {names.listing([v.get('name') or v['id'] for v in dead])}: "
                       + ("it cannot fail, or it fails now." if len(dead) == 1 else "they cannot fail, or they fail now.") + names.ref([v["id"] for v in dead]))
    if "formal" in ran:
        rec = c.run / "formal-recheck.json"
        if rec.is_file():
            rs = json.loads(rec.read_text()).get("results", [])
            green = sum(r["status"] == "green" for r in rs)
            out.append(f"Checked: {prompt.n_of(len(rs), 'formal check')} at the review-branch tip. Passed: {green} of {len(rs)}.")
    after = verdict_of(data)
    moved = [(cid, before.get(cid), v) for cid, v in after.items() if before.get(cid) != v and before]
    up = [m for m in moved if m[1] in rank and m[2] in rank and rank[m[2]] < rank[m[1]]]
    down = [m for m in moved if m[1] in rank and m[2] in rank and rank[m[2]] > rank[m[1]]]
    for cid, _, v in up[:3]:
        out.append(f"'{names.of(data, cid)}' is now {dict(VERDICT_WORDS)[v]}." + names.ref([cid]))
    for cid, _, v in down[:3]:
        out.append(f"'{names.of(data, cid)}' dropped to {dict(VERDICT_WORDS)[v]}." + names.ref([cid]))
    if len(moved) > 6:
        out.append(f"{prompt.n_of(len(moved) - min(len(up), 3) - min(len(down), 3), 'other claim')} changed too.")
    if not moved and ran:
        out.append("Changed for you: no verdict changed.")
    if up and data.get("promises"):
        p = next((p for p in data["promises"] if up[0][0] in p["claims"]), None)
        if p and opener.status(c.run, data)["present"]:
            row = opener.open_page(c.run, data, anchor=p["id"], no_open=no_open, why="stop report")
            if row["opened"]:
                out.append("I opened its promise in the explainer.")
    return out


# ---- progress -----------------------------------------------------------------------------------

PROGRESS: list = [None]   # a writer for NDJSON events in --json mode, else None


def progress(item_id: str, ok: bool, text: str) -> None:
    """One plain line per finished item ("... ✓", or "... ✗ <reason>"). --json writes NDJSON events."""
    line = f"{text} {'✓' if ok else '✗'}" if ok or "✗" not in text else text
    if PROGRESS[0]:
        PROGRESS[0](json.dumps({"event": "progress", "id": item_id, "ok": ok, "text": line}, ensure_ascii=False))
    else:
        print(line)
        sys.stdout.flush()


def step_progress(c: context.Ctx, st: dict, step: str, code: int, stop: str | None, scope: list[str] | None) -> None:
    import names
    data = c.data() or {}
    if code:
        progress(step, False, f"{STEP_NAME.get(step, step)} ✗ {(st.get('failed') or {}).get('plain') or 'it stopped; its output is above.'}")
        return
    if step == "map":
        progress("map", True, "Map: the verdicts are up to date at the review-branch tip")
    elif step == "probe":
        # One line per claim (promise -> claim -> check): how many of its checks in scope caught their planted bug.
        for cl in data.get("claims", []):
            checks = [v for v in names.checks_of(data, cl) if "command" in v and (scope is None or v["id"] in scope)]
            if not checks:
                continue
            who = names.of(data, cl["id"])
            who = who[:1].upper() + who[1:]
            import onto
            b = onto.bar(data, cl)
            bar = f" · met the {b['need']} bar" if b["met"] else f" · below the {b['need']} bar"
            caught = [v for v in checks if v.get("state") == "proven"]
            dead = [v for v in checks if v.get("state") in ("cannot-fail", "failing", "broken")]
            n = len(checks)
            if len(caught) == n:
                progress(cl["id"], b["met"], f"{who}: {'its check' if n == 1 else f'{n} of {n} checks'} caught the planted bug" + ("" if n == 1 else "s") + bar)
            elif dead:
                v = dead[0]
                why = "stayed green on its planted bug, so it cannot fail" if v.get("state") == "cannot-fail" else "fails without a planted bug"
                progress(cl["id"], False, f"{who}: ✗ {len(caught)} of {n} checks caught their planted bug; {v.get('name') or 'one check'} {why}{bar}")
            else:
                progress(cl["id"], False, f"{who}: ✗ {len(caught)} of {n} checks caught their planted bug; the rest ran no planted bug{bar}")
    elif step == "formal":
        rec = c.run / "formal-recheck.json"
        if rec.is_file():
            for r in json.loads(rec.read_text()).get("results", []):
                what = "the trace replay" if r["id"].endswith("-replay") else ("the model check" if "tlc" in " ".join(r["argv"]).lower() or ".tla" in " ".join(r["argv"]) else "the proof build")
                progress(r["id"], r["status"] == "green", f"Formal: {what} {'passed' if r['status'] == 'green' else '✗ ' + r['status']} at the review-branch tip")
    elif step in ("trim", "ready", "explain", "close") and not stop:
        progress(step, True, {"trim": "Trim: excess code and doubled unit tests checked", "ready": "Ready: the four gates computed",
                              "explain": "Explain: the explainer and the PR section built", "close": "Close: your answers applied"}[step])


STEP_NAME = {"map": "Map", "probe": "Probe", "formal": "Formal re-check", "close": "Close", "trim": "Trim", "ready": "Ready", "explain": "Explain"}


# ---- the verb -----------------------------------------------------------------------------------

class Failed(Exception):
    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.code = code


def main(c: context.Ctx, argv: list[str]) -> int:
    if not c.json:
        return _main(c, argv)
    # --json always prints one JSON object: the step output goes to stderr, and an error is {"error": ...}.
    sys.stdout.flush()
    saved = os.dup(1)
    os.dup2(2, 1)
    real_fail = tm.fail

    def fail(message: str, code: int = 2) -> None:
        raise Failed(message, code)
    tm.fail = fail
    out = os.fdopen(os.dup(saved), "w")
    PROGRESS[0] = lambda line: (out.write(line + "\n"), out.flush())
    payload: dict | None = None
    code = 1
    try:
        code, payload = _main(c, argv, capture=True)
    except Failed as exc:
        code, payload = exc.code, {"error": str(exc), "exit": exc.code}
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        payload = {"error": f"review stopped (exit {code})", "exit": code}
    except Exception as exc:  # noqa: BLE001
        code, payload = 1, {"error": f"{type(exc).__name__}: {exc}", "exit": 1}
    finally:
        tm.fail = real_fail
        PROGRESS[0] = None
        out.close()
        sys.stdout.flush()
        os.dup2(saved, 1)
        os.close(saved)
    print(json.dumps(payload if payload is not None else {"error": "review printed no result", "exit": code}, indent=2, ensure_ascii=False))
    sys.stdout.flush()
    return code


def _main(c: context.Ctx, argv: list[str], capture: bool = False):
    import argparse
    ap = argparse.ArgumentParser(prog="understando review", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pr", nargs="?")
    ap.add_argument("--head")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--through", action="store_true")
    ap.add_argument("--answers")
    ap.add_argument("--guard")
    ap.add_argument("--full", action="store_true", help="also print the full state")
    ap.add_argument("--verbose", action="store_true", help="also print the details: IDs, SHAs and paths")
    ap.add_argument("--merge", action="store_true", help="merge the new PR commits into the ready branch (the user's pick)")
    ap.add_argument("--skip-merge", action="store_true")
    ap.add_argument("--show-new", action="store_true", help="list the new PR commits and their files")
    ap.add_argument("--link", choices=["yes", "no"], help="link the first proposed new test to its claim, or not")
    ap.add_argument("--teach", action="store_true", help="the next teach turn")
    ap.add_argument("--skip-teach", action="store_true")
    ap.add_argument("--skip", metavar="STEP", help="mark a failed step as skipped")
    ap.add_argument("--no-open", action="store_true", help="do not open the explainer; print its path")
    ap.add_argument("--step", action="store_true", help="stop after each stage (the old phase-by-phase stops); the default runs through")
    ap.add_argument("--no-rebuild", action="store_true", help="do not rebuild a stale explainer at the first stop")
    args = ap.parse_args(argv)
    pr = args.pr or c.pr
    if not pr:
        tm.fail("usage: understando review <pr>", 2)
    answers = json.loads(Path(args.answers).read_text(encoding="utf-8")) if args.answers else {}
    go = str(answers.get("go", "")).lower()
    step_mode = args.step or go == "step"
    go = args.through or args.go or go in ("step", "go", "yes", "run through", "through", "all")
    # Run through is the default: it stops only for the decisions that are the user's (the merge of new
    # PR commits, the CI approval, claim wording, waivers, invariants and paid steps). --step stops after each stage.
    through = go and not step_mode
    no_open = args.no_open or bool(os.environ.get("UNDERSTANDO_NO_OPEN"))
    VERBOSE[0] = args.verbose

    def done(code: int, payload: dict, text: str):
        if capture:
            return code, payload
        print(text)
        return code

    if args.guard:
        ctx = resolve(pr, c.repo if c.explicit_repo else None, args.head)
        run = Path(ctx["run"])
        cfg = config.load(ctx["name"])
        bad = guard(run, [f for f in args.guard.split(",") if f], cfg)
        return done(1 if bad else 0, {"refusals": bad}, "\n".join(bad) if bad else f"ok: {args.guard} may change on {ctx['branch']} now")

    ctx = resolve(pr, c.repo if c.explicit_repo else None, args.head)
    run = Path(ctx["run"])
    refusal = context.refuse_run_write(run, Path(ctx["repo"]))
    if refusal:
        tm.fail(refusal, 1)
    run.mkdir(parents=True, exist_ok=True)
    st = {**load_state(run), **ctx}
    if not st.get("started_at") or st.get("head_at_start") != ctx["head"]:
        st.update(started_at=tm.now(), head_at_start=ctx["head"], done=[], teach=None, failed=None, opened=None)
    st.update(setup_worktree(ctx))
    if ctx["offline"] and (st.get("pr_new") or {}).get("commits") and (st.get("merge") or {}).get("head") != ctx["head"]:
        st["merge"] = {"head": ctx["head"], "decision": "skipped", "offline": True, "at": tm.now()}
        journal.append(Path(ctx["run"]) / "journal.jsonl", "decision", "review: the merge question is skipped, GitHub is not reachable", Path(ctx["repo"]))
    cfg = config.load(ctx["name"])
    dropped = config.drop_inherited_key(cfg)
    c = context.Ctx(run, Path(ctx["repo"]), ctx["pr"], c.json)
    context.save_mode({"on": True, "run": str(run), "repo": ctx["repo"], "pr": ctx["pr"], "since": tm.now(),
                       "autonomy": False, "with": context.load_mode().get("with", []), "review": True})
    journal.append(c.journal, "decision", f"review {ctx['slug']}#{pr}: start at {ctx['head'][:10]}", c.repo,
                   evidence=str(state_path(run)), result=f"worktree {st['made']}" + (f", pulled {st['pulled']['commits']}" if st.get("pulled") else ""))
    out_lines: list[str] = []

    # The user's pick on the merge question.
    if answers.get("merge") in ("yes", "merge") or args.merge:
        if not (st.get("pr_new") or {}).get("commits"):
            out_lines.append("review: the review branch already has every PR commit; nothing to merge.")
        else:
            before_tip = st["tip"]
            ok, what = merge_head(st)
            if not ok:
                save_state(run, st)
                return done(1, {"merged": False, "error": what}, f"STOP: {what}")
            st["merge"] = {"head": st["head"], "decision": "merged", "from": before_tip, "to": what, "at": tm.now()}
            st["tip"] = what
            st["pr_new"] = pr_new(Path(st["worktree"]), st["head"], what)
            st["done"] = [x for x in st.get("done", []) if x not in ("map", "probe", "formal")]
            journal.append(c.journal, "decision", f"review: merge the PR head {st['head'][:10]} into {st['branch']} (the user's pick)", c.repo,
                           result=f"{before_tip[:10]} -> {what[:10]}, no rebase, no push")
            out_lines.append("Merged the new PR commits into the review branch (a normal merge; nothing was pushed). The re-check covers what they touch.")
    if answers.get("merge") == "skip" or args.skip_merge:
        st["merge"] = {"head": st["head"], "decision": "skipped", "at": tm.now()}
        journal.append(c.journal, "decision", f"review: skip the merge of {st['head'][:10]} (the user's pick)", c.repo)
    if args.show_new:
        new = st.get("pr_new") or {}
        lines = [f"{sha} {subj}" for sha, subj in zip(new.get("shas", []), new.get("subjects", []))]
        files = new.get("files", [])
        text = "\n".join(["The new PR commits:"] + [f"  {x}" for x in lines] + [f"They change {len(files)} files:"] + [f"  {f}" for f in files[:40]])
        return done(0, {"pr_new": new}, text)

    if answers.get("ci") == "approve" or not (run / "ci.json").is_file() or (ci.load(run) or {}).get("head") != ctx["head"] \
            or (ci.load(run) or {}).get("ready") != st["tip"]:
        base = repoinfo.rev(Path(ctx["repo"]), f"origin/{ctx['base_name']}") or repoinfo.rev(Path(ctx["repo"]), ctx["base_name"])
        prof = ci.build(Path(ctx["repo"]), ctx["head"], base, st["tip"], ctx["pr"])
        ci.save(run, prof)
    if answers.get("ci") == "approve" and not ci.approved(ci.load(run)):
        prof = ci.load(run)
        line = ci.approve(prof, answers.get("ci_project"), "user (answer file)")
        (run / "ci.json").write_text(json.dumps(prof, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        journal.append(c.journal, "decision", line + " (answer file)", c.repo, result=prof["approval"]["digest"])

    # The user's pick on a link question: the first proposed new test.
    link = answers.get("link") or args.link
    if link:
        props = link_proposals(c, st)
        if props:
            import newtests
            p = props[0]
            st.setdefault("links", {})[p["test"]] = "linked" if link == "yes" else "skipped"
            if link == "yes":
                data = c.data()
                import cli
                cli.snapshot_before(c)
                v = newtests.link(data, p, "user (review)")
                tm.save(data, c.map)
                journal.append(c.journal, "decision", f"review: link the new test {p['test']} to {p['claim']} as {v['id']} (the user's pick)", c.repo)
                out_lines.append(f"Linked the new test to '{__import__('names').of(data, p['claim'])}'. The re-check probes it with its planted bug." + __import__("names").ref([v["id"], p["claim"]]))

    if args.skip:
        if (st.get("failed") or {}).get("step") == args.skip or args.skip in STEPS:
            st["done"] = list(dict.fromkeys(st.get("done", []) + [args.skip]))
            st.setdefault("skipped", []).append(args.skip)
            st["failed"] = None
            journal.append(c.journal, "decision", f"review: skip the {args.skip} step (the user's pick)", c.repo)
    if args.skip_teach:
        st["teach"] = {"turn": len(TEACH_LEVELS), "skipped": True}
    if go:
        st["through"] = through

    import doctor
    import signals
    sig = signals.collect(c, ctx["head"])
    doc, _ = doctor.findings(c, ctx["head"], formal=False)
    prof = ci.load(run)
    s = summary(c, st, sig, doc, prof, cfg)
    if dropped:
        s["dropped_env"] = dropped
    st["summary_at"] = tm.now()
    remaining = [x for x in STEPS if x not in st.get("done", [])]
    st["next"] = remaining[0] if remaining else None
    import opener
    # The first stop opens the explainer at the merge verdict, before the first question.
    first = st.get("opened") is None or (st.get("opened") or {}).get("tip") != st["tip"]
    page = opener.status(run, c.data())
    if first and not go and page["present"] and page["stale"] and not args.no_rebuild and (run / "explain.json").is_file():
        import cli
        with __import__("contextlib").redirect_stdout(sys.stderr):
            rebuilt = cli.run_verb("explain", ["--html"], c) == 0
        progress("explainer", rebuilt, f"The explainer was out of date ({page['why']}); I rebuilt it" if rebuilt
                 else f"The explainer is out of date ({page['why']}) ✗ the rebuild failed; its output is above")
    if first and opener.status(run, c.data())["present"] and not go:
        row = opener.open_page(run, c.data(), level="verdict", no_open=no_open, why="review start")
        st["opened"] = {**row, "tip": st["tip"]}
    save_state(run, st)
    import prompt

    def ask(extra: dict):
        q = build_prompt(c, st, s, sig, answers, doc)
        text = "\n".join(out_lines + ([""] if out_lines else [])) + prompt.render(q, verbose=args.verbose) + ("\n\n" + summary_text(s) if args.full else "")
        save_state(run, st)
        return done(0, {**s, **extra, "prompt": q, "state": str(state_path(run)), "next": st.get("next"), "done": st.get("done", []),
                        "said": out_lines, "opened": st.get("opened")}, text)

    if args.teach:
        text = teach_turn(c, st, no_open)
        save_state(run, st)
        return done(0, {"teach": st["teach"], "reply": text, "opened": (st.get("opened_log") or [None])[-1]}, text)
    if not go:
        return ask({"stopped": "before " + (st["next"] or "nothing"), "awaiting": "go"})
    if (st.get("pr_new") or {}).get("commits") and (st.get("merge") or {}).get("head") != st["head"]:
        return ask({"stopped": "merge question", "awaiting": "merge"})
    if not ci.approved(prof):
        return ask({"stopped": "ci approval", "awaiting": "ci"})
    code = 0
    stage = None
    before = verdict_of(c.data())
    scope = probe_scope(c, st)
    ran: list[str] = []
    st["failed"] = None
    for step in remaining:
        if stage and stage_of(step) != stage and not through:
            break
        stage = stage_of(step)
        t0 = time.monotonic()
        try:
            code, stop = run_step(c, st, step, answers)
        except Exception as exc:  # noqa: BLE001
            code, stop = 1, None
            st["failed"] = {"step": step, "reason": f"{type(exc).__name__}: {exc}", "plain": "it hit an internal error. The details say which.", "at": tm.now(), "tip": st.get("tip")}
        st.setdefault("timings", {})[step] = round(time.monotonic() - t0, 1)
        if code == 0 and not stop:
            st["done"] = st.get("done", []) + [step]
            ran.append(step)
        elif code and not st.get("failed"):
            st["failed"] = {"step": step, "reason": stop or f"{step} exited {code}", "plain": (stop or f"it exited with code {code}; its output is above.").rstrip(".") + ".",
                            "at": tm.now(), "tip": st.get("tip")}
        st["next"] = next((x for x in STEPS if x not in st["done"]), None)
        save_state(run, st)
        step_progress(c, st, step, code, stop, scope)
        journal.append(c.journal, "result", f"review step {step}: exit {code}", c.repo, result=stop or "")
        if stop == "close":
            break
        if stop and not code:
            print(f"\nSTOP: {stop}")
            return done(code, {"stopped": stop}, "")
        if code:
            print(f"\nSTOP: {step} exited {code}. review records it; the next `understando review {pr}` asks to retry or skip it.")
            sig = signals.collect(c, ctx["head"])
            s = summary(c, st, sig, doc, ci.load(run), cfg)
            return ask({"stopped": f"{step} failed", "failed": st["failed"]}) if capture else (print("\n" + prompt.render(build_prompt(c, st, s, sig, answers, doc), verbose=args.verbose)) or code)
    report = stop_report(c, st, before, ran, scope, no_open)
    if report:
        print("\n" + "\n".join(report))
    if st["next"] is None:
        print("\nreview: every step is done. The user merges; understando opens no PR and edits no PR.")
        return done(code, {"done": st["done"], "report": report}, "")
    sig = signals.collect(c, ctx["head"])
    s = summary(c, st, sig, doc, ci.load(run), cfg)
    if capture:
        return ask({"report": report})
    print("\n" + prompt.render(build_prompt(c, st, s, sig, answers, doc), verbose=args.verbose))
    return code
