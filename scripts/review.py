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
    info = repoinfo.gh_pr(pr, slug)
    head = (info or {}).get("headRefOid") or head_opt
    if not head:
        tm.fail("review: no PR head. gh is missing or failed; pass --head SHA", 2)
    if head_opt and info and info.get("headRefOid") and head_opt != info["headRefOid"]:
        print(f"review: --head {head_opt[:10]} differs from gh ({info['headRefOid'][:10]}); using gh", file=sys.stderr)
    base_name = (info or {}).get("baseRefName") or "main"
    cfg = config.load(name)
    run = config.runs_root() / name / str(pr)
    branch = cfg["ready_branch"].format(pr=pr)
    wt = repo / cfg["worktree_root"] / f"understando-{pr}-ready"
    return {"pr": str(pr), "repo": str(repo), "slug": slug or name, "name": name, "head": head, "base_name": base_name,
            "run": str(run), "branch": branch, "worktree": str(wt), "config": cfg.get("path"), "config_present": cfg["present"],
            "gh": bool(info), "state": (info or {}).get("state")}


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
            out = git_q(wt, "-c", "pull.rebase=false", "pull", "-q", "--no-rebase", "--no-edit", "origin", branch)
            if out.returncode:
                tm.fail(f"review: `git pull --no-rebase` in {wt} failed. Resolve it by hand, then run review again:\n{out.stderr.strip()}", 1)
            pulled = {"commits": behind, "from": before, "to": repoinfo.rev(wt, "HEAD")}
    tip = repoinfo.rev(wt, "HEAD")
    return {"worktree": str(wt), "made": made, "pulled": pulled, "tip": tip,
            "ahead_of_head": int(git_q(repo, "rev-list", "--count", f"{head}..{tip}").stdout.strip() or 0)}


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
                 "locks": lock.live(Path(st["run"]))}
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

def call(c: context.Ctx, verb: str, argv: list[str]) -> int:
    import cli
    print(f"\n== review: {verb} {' '.join(argv)}".rstrip())
    sys.stdout.flush()
    return cli.run_verb(verb, argv, c)


def reverify_map(c: context.Ctx, st: dict) -> None:
    """Point the verifiers of the claims that the ready branch changed at the ready tip, so probe
    runs them at the fix. The map records the ready branch and its tip."""
    data = c.data()
    if not data or not st.get("tip") or st["tip"] == data["head"]:
        return
    import signals
    rv = signals.ready_changes(c, data, st["branch"], st["tip"])
    data["ready"] = {"branch": st["branch"], "head": st["tip"]}
    moved = []
    for v in data["verifiers"]:
        if v["id"] in rv["verifiers"] and "command" in v and v.get("at") != st["tip"]:
            v["at"] = st["tip"]
            moved.append(v["id"])
    tm.save(data, c.map)
    if moved:
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
    (c.run / "formal-recheck.json").write_text(json.dumps({"tip": st["tip"], "at": tm.now(), "results": results}, indent=2) + "\n")
    side = c.run / "formal" / "verifiers.json"
    if side.is_file():
        print(f"review: formal: re-run the frog scripts of {c.run / 'formal'} at the ready tip, re-stamp each record "
              f"(formal_record.py stamp), then run `understando formalize --sidecar {side}`. The user starts formalize.")
    return 0 if all(r["status"] == "green" for r in results) else 1


def run_step(c: context.Ctx, st: dict, step: str, answers: dict) -> tuple[int, str | None]:
    """(exit, stop reason). A stop reason ends the run, also under "run through"."""
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


def next_info(c: context.Ctx, st: dict, stage: str, answers: dict) -> dict:
    import prompt
    import signals
    data = c.data() or {}
    pr = st["pr"]
    timings = st.get("timings") or {}

    def took(*steps: str) -> str | None:
        rec = [timings[x] for x in steps if x in timings]
        return (prompt.human_seconds(sum(rec)) + " (the last recorded run)") if rec else None

    if stage == "check":
        if not data:
            return {"step": "map", "does": "Write the claim ledger (commands/map.md), then map", "scope": "every claim",
                    "cost": "$0, no model call by the CLI", "time": "unknown: no recorded run", "writes": "trust-map.json in the run folder"}
        scope = probe_scope(c, st)
        vids = None if scope is None else set(scope)
        sig = signals.collect(c, st.get("head"))
        bugs = [b for b in sig["discover"].get("bug_changes", []) if b["changed"]]
        rv = (sig.get("ready_branch") or {}).get("reverify") or {}
        claims = sorted({x for b in bugs for x in b["claims"]} | set(rv.get("claims") or []), key=lambda x: (len(x), x))
        sec, n = recorded_seconds(data, vids)
        sec += timings.get("map", 5)
        keyed = paid_in(c, data, vids, answers.get("paid") or [])
        usd = sum(float((v.get("cost") or {}).get("usd") or 0) for v in keyed)
        calls = sum(int((v.get("cost") or {}).get("model_calls") or 1) for v in keyed)
        what = (f"Re-checks possible bug {', '.join(b['invariant'] for b in bugs)} on the changed code: " if bugs else "") \
            + "map updates the verdicts at the ready tip, then " \
            + ("probe runs every verifier and control" if scope is None else
               (f"probe runs {prompt.n_of(len(scope), 'verifier')} and their controls" if scope else "probe has nothing to run (no changed verifier)"))
        return {"step": "check", "does": what,
                "scope": "every claim" if scope is None else
                         "; ".join(x for x in [f"claims {signals.ids(claims)}" if claims else "",
                                                f"verifiers {signals.ids(scope)}" if scope else "no verifier"] if x),
                "cost": "$0, no model call" if not keyed else
                        f"$0, no model call; {signals.ids([v['id'] for v in keyed])} need the model key (about ${usd:.2f}, {calls} model calls) and run only after your yes",
                "time": (prompt.human_seconds(sec) + f" (from {n} recorded runs)") if n else (took("map", "probe") or "unknown: no recorded run"),
                "writes": "trust-map.json and history/ in the run folder; no commit"}
    if stage == "trim":
        return {"step": "trim", "does": "Finds excess code, and deletes each unit test that an e2e test already covers, after probe shows the e2e test goes red",
                "scope": f"the {sum(1 for v in data.get('verifiers', []) if 'unit' in str(v.get('kind', '')))} unit-test verifiers and the changed code",
                "cost": "$0, no model call", "time": took("trim") or "unknown: no recorded run",
                "writes": f"trim.json; deletions are commits on {st['branch']}"}
    if stage == "ship":
        return {"step": "ship", "does": "ready --report prints the four gates; explain builds the explainer and pr-section.md",
                "scope": "the whole trust map", "cost": "$0, no model call", "time": took("ready", "explain") or "unknown: no recorded run",
                "writes": "ready.json, explainer.mdx, chapters/, pr-section.md and GLOSSARY.md in the run folder; nothing edits the PR"}
    return {"step": "close", "does": "One question per open claim", "scope": "the open claims, riskiest first", "cost": "$0",
            "time": "a few minutes per claim", "writes": f"trust-map.json; a new test is a commit on {st['branch']}"}


def situation(s: dict, st: dict, sig: dict) -> list[str]:
    """At most five lines: what moved, where the PR stands, what affects the next step."""
    import prompt
    lines = []
    tmap = sig.get("trust_map") or {}
    moved = f"PR head {st['head'][:10]}" + ("" if not tmap.get("present") else
                                            (" (the map head)" if tmap.get("fresh") else f" (the map is at {tmap['head'][:10]})"))
    rb = sig.get("ready_branch") or {}
    rv = rb.get("reverify") or {}
    if st.get("tip") and st["tip"] != st["head"]:
        since = rv.get("since") or st["head"]
        commits = subprocess.run(["git", "-C", st["repo"], "log", "--format=%h", "--reverse", f"{since}..{st['tip']}"],
                                 capture_output=True, text=True).stdout.split()
        moved += f". {st['branch']} at {st['tip'][:10]}: {prompt.n_of(len(commits), 'commit')} after the map" + (f" ({', '.join(commits[:4])}{' ...' if len(commits) > 4 else ''})" if commits else "")
    if st.get("pulled"):
        moved += f"; pulled {st['pulled']['commits']} just now"
    lines.append(moved + ".")
    if s.get("trust_map", 1) is None:
        lines.append("No trust map yet: the first step writes it.")
    else:
        n_open = len(s.get("open") or [])
        g = s.get("gates")
        failing = [k for k, v in (g or {}).items() if k.startswith("gate") and not v] if g and not g.get("stale") else []
        blockers = n_open + len(failing)
        verdict = "ready to merge" if g and g.get("pass") and not g.get("stale") and not n_open else \
            f"not ready, {prompt.n_of(blockers, 'blocker')} (" + ", ".join(x for x in [prompt.n_of(n_open, 'open claim') if n_open else "",
                                                                       f"{', '.join(failing)} fail" if failing else "",
                                                                       "gates not computed at this head" if not g or g.get("stale") else ""] if x) + ")"
        lines.append("Verdicts: " + ", ".join(f"{k} {v}" for k, v in (s.get("verdicts") or {}).items()) + f". Merge: {verdict}.")
    bugs = [b for b in sig.get("discover", {}).get("bug_changes", []) if b["changed"]]
    if bugs:
        b = bugs[0]
        lines.append(f"{st['branch']} changed {', '.join(b['where'])}, the code of possible bug {b['invariant']}"
                     + (f" ({', '.join(b['commits'])})" if b["commits"] else "") + ": re-check it before discover.")
    elif rv.get("claims"):
        lines.append(f"{st['branch']} changed the code or checks of claims {', '.join(rv['claims'][:6])}: re-check them first.")
    if s["ci"]["present"] and not s["ci"]["approved"]:
        prof = ci.load(Path(st["run"])) or {}
        lines.append(f"CI: {prompt.n_of(s['ci']['commands'], 'command')} from your workflows, because {ci.why_line(prof)}; not approved yet." if prof
                     else "CI: no profile yet.")
    if s["locks"]:
        h = s["locks"][0]
        lines.append(f"Lock: {h['owner']} holds {h['verb']} on {', '.join(h['paths'])}.")
    return lines[:5]


def build_prompt(c: context.Ctx, st: dict, s: dict, sig: dict, answers: dict) -> dict:
    import close
    import prompt
    pr = st["pr"]
    stage = next_stage(st.get("done", []))
    sit = situation(s, st, sig)
    prof = ci.load(c.run)
    if stage is None:
        sec = c.run / "pr-section.md"
        return prompt.make(sit, "The review is complete. What next?",
                           [prompt.option("Show pr-section.md", f"Prints {sec} for you to paste into the PR body. understando never edits the PR.",
                                          f"cat {sec}"),
                            prompt.option("Review again", "Resolves the PR again, pulls the ready branch, and asks the next question.",
                                          f"understando review {pr}")])
    nxt = next_info(c, st, stage, answers)
    if stage != "close" and not ci.approved(prof) and prof:
        q = ci.question(prof, then=f"review runs {STAGE_NAME[stage]}")
        for o in q["options"]:
            if o.get("run", "").startswith("understando ci --approve"):
                o["run"] += f"; then understando review {pr} --go"
        q["situation"] = [x for x in sit if not x.startswith("CI:")][:4] + q["situation"]
        q["next"] = nxt
        prompt.check(q)
        return q
    if stage == "close":
        data = c.data() or {}
        q = close.question(data, pr)
        if q:
            for o in q["options"]:
                if o.get("choice"):
                    o["run"] = f"understando review {pr} --go --answers <file with {{\"close\": {{\"answers\": [{{\"claim\": \"{q['claim']}\", \"choice\": \"{o['choice']}\", ...}}]}}}}>"
            q["situation"] = sit[1:2] + q["situation"]
            prompt.check(q)
            return q
    opts = [prompt.option(f"Run {STAGE_NAME[stage]}", nxt["does"] + ".", f"understando review {pr} --go"),
            prompt.option("Run through", "Runs every stop that needs no decision. It still stops for each open claim, the CI approval "
                          "and each paid step.", f"understando review {pr} --through")]
    keyed = paid_in(c, c.data() or {}, None if (stage != "check" or probe_scope(c, st) is None) else set(probe_scope(c, st) or []),
                    answers.get("paid") or []) if stage == "check" and c.data() else []
    if keyed:
        ids = ",".join(v["id"] for v in keyed)
        opts.insert(1, prompt.option(f"Run it with the paid {ids}", f"Also runs {ids} with the model key: {nxt['cost'].split('; ', 1)[-1]}.",
                                     f"understando review {pr} --go --answers <file with {{\"paid\": {json.dumps(ids.split(','))}}}>"))
    return prompt.make(sit, f"Run {STAGE_NAME[stage]}?", opts, nxt)


# ---- the verb -----------------------------------------------------------------------------------

def main(c: context.Ctx, argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="understando review", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pr", nargs="?")
    ap.add_argument("--head")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--through", action="store_true")
    ap.add_argument("--answers")
    ap.add_argument("--guard")
    ap.add_argument("--full", action="store_true", help="also print the full state")
    args = ap.parse_args(argv)
    pr = args.pr or c.pr
    if not pr:
        tm.fail("usage: understando review <pr>", 2)
    answers = json.loads(Path(args.answers).read_text(encoding="utf-8")) if args.answers else {}
    go = str(answers.get("go", "")).lower()
    through = args.through or go in ("run through", "through", "all")
    go = through or args.go or go in ("step", "go", "yes")

    if args.guard:
        ctx = resolve(pr, c.repo if c.explicit_repo else None, args.head)
        run = Path(ctx["run"])
        cfg = config.load(ctx["name"])
        bad = guard(run, [f for f in args.guard.split(",") if f], cfg)
        print("\n".join(bad) if bad else f"ok: {args.guard} may change on {ctx['branch']} now")
        return 1 if bad else 0

    ctx = resolve(pr, c.repo if c.explicit_repo else None, args.head)
    run = Path(ctx["run"])
    run.mkdir(parents=True, exist_ok=True)
    st = {**load_state(run), **ctx}
    if not st.get("started_at") or st.get("head_at_start") != ctx["head"]:
        st.update(started_at=tm.now(), head_at_start=ctx["head"], done=[])
    st.update(setup_worktree(ctx))
    cfg = config.load(ctx["name"])
    dropped = config.drop_inherited_key(cfg)
    c = context.Ctx(run, Path(ctx["repo"]), ctx["pr"], c.json)
    context.save_mode({"on": True, "run": str(run), "repo": ctx["repo"], "pr": ctx["pr"], "since": tm.now(),
                       "autonomy": False, "with": context.load_mode().get("with", []), "review": True})
    journal.append(c.journal, "decision", f"review {ctx['slug']}#{pr}: start at {ctx['head'][:10]}", c.repo,
                   evidence=str(state_path(run)), result=f"worktree {st['made']}" + (f", pulled {st['pulled']['commits']}" if st.get("pulled") else ""))
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
    save_state(run, st)
    import prompt

    def ask(extra: dict) -> None:
        q = build_prompt(c, st, s, sig, answers)
        text = prompt.render(q) + ("\n\n" + summary_text(s) if args.full else "")
        context.emit(c, {**s, **extra, "prompt": q, "state": str(state_path(run)), "next": st.get("next"), "done": st.get("done", [])}, text)

    if not go:
        ask({"stopped": "before " + (st["next"] or "nothing"), "awaiting": "go"})
        return 0
    if not ci.approved(prof):
        ask({"stopped": "ci approval", "awaiting": "ci"})
        return 0
    code = 0
    stage = None
    for step in remaining:
        if stage and stage_of(step) != stage and not through:
            break
        stage = stage_of(step)
        t0 = time.monotonic()
        code, stop = run_step(c, st, step, answers)
        st.setdefault("timings", {})[step] = round(time.monotonic() - t0, 1)
        if code == 0 and not stop:
            st["done"] = st.get("done", []) + [step]
        st["next"] = next((x for x in STEPS if x not in st["done"]), None)
        save_state(run, st)
        journal.append(c.journal, "result", f"review step {step}: exit {code}", c.repo, result=stop or "")
        if stop == "close":
            break
        if stop:
            print(f"\nSTOP: {stop}")
            return code
        if code:
            print(f"\nSTOP: {step} exited {code}. Fix it, then run `understando review {pr} --go` again.")
            return code
    if st["next"] is None:
        print("\nreview: every step is done. The user merges; understando opens no PR and edits no PR.")
        return code
    sig = signals.collect(c, ctx["head"])
    s = summary(c, st, sig, doc, ci.load(run), cfg)
    print("\n" + prompt.render(build_prompt(c, st, s, sig, answers)))
    return code
