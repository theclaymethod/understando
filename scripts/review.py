"""understando review: a full PR review from one line. `understando review <pr>`.

    understando review N [--head SHA]            resolve, set up, summarise, then stop for the user's go
    understando review N --go                    run the next step, then stop
    understando review N --through               run every step that is left ("run through")
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

Then: mode on, ci (ci.json), signals, doctor, and a short summary. It stops for the user's go.
The steps after the go: map, probe, formal (only when a formal check must run again), close, trim,
ready --report, explain. Each step stops for the user, unless the user said "run through". close
stops for the user's choices in any mode. explain prints pr-section.md; nothing edits the PR.

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
        extra = ["--paid", ",".join(answers["paid"])] if answers.get("paid") else []
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
                return call(c, "close", ["--answers", fh.name]), None
            finally:
                os.unlink(fh.name)
        code = call(c, "close", ["--list"])
        data = c.data() or {}
        if any(x.get("verdict") not in CLOSED and not x.get("waiver") for x in data.get("claims", [])):
            return code, ("close needs the user's choice for each open claim. Ask one claim at a time (commands/close.md), "
                          "then run review with --answers holding {\"close\": {...}}.")
        return code, None
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
        prof["approval"] = {"digest": prof["digest"], "at": tm.now(), "by": "user (answer file)"}
        (run / "ci.json").write_text(json.dumps(prof, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        journal.append(c.journal, "decision", "approved the CI profile (answer file)", c.repo, result=prof["digest"])
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

    def report(extra: dict, text: str) -> None:
        context.emit(c, {**s, **extra, "state": str(state_path(run)), "next": st.get("next"), "done": st.get("done", [])}, text)

    if not go:
        report({"stopped": "before " + (st["next"] or "nothing"), "awaiting": "go"},
               summary_text(s) + f"\n\nSTOP: wait for the user's go. Next step: {st['next'] or 'none, the review is complete'}. "
               "On a go, run `understando review " + pr + " --go` (one step) or `--through` (run through).")
        return 0
    if not ci.approved(prof):
        report({"stopped": "ci approval", "awaiting": "ci"},
               summary_text(s) + "\n\nSTOP: the CI profile is not approved. Show `understando ci` to the user; after a clear yes, "
               "the user runs `understando ci --approve`.")
        return 0
    print(summary_text(s))
    code = 0
    for step in remaining:
        code, stop = run_step(c, st, step, answers)
        if code == 0 and not stop:
            st["done"] = st.get("done", []) + [step]
        st["next"] = next((x for x in STEPS if x not in st["done"]), None)
        save_state(run, st)
        journal.append(c.journal, "result", f"review step {step}: exit {code}", c.repo, result=stop or "")
        if stop:
            print(f"\nSTOP: {stop}")
            return code
        if code:
            print(f"\nSTOP: {step} exited {code}. Fix it, then run `understando review {pr} --go` again.")
            return code
        if not through:
            print(f"\nSTOP: {step} is done. Next: {st['next'] or 'none'}. Wait for the user's go.")
            return 0
    print("\nreview: every step is done. The user merges; understando opens no PR and edits no PR.")
    return code
