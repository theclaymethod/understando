"""understando ci: the repo's reviewed CI profile for one PR, as $R/ci.json.

    understando ci [--pr N] [--head SHA] [--base REF] [--ready REF]     derive and write ci.json; run nothing
    understando ci --approve [--project NAME]                             record the user's yes (the user only)
    understando ci --check-argv ARG...                                    say which profile command allows an argv

It reads repo files as data, at the PR head, with `git show`. It never runs a repo command:

1. AGENTS.md (the root one, and the one of each touched project): the lines that name the CI
   profile, and each fenced command, marked `in_profile` or not. A command that only a doc names
   never goes into the profile.
2. catalog.toml (a monorepo catalog), when present: the projects, and which of them the PR touches.
   A changed path outside every project fails open: every project counts as touched.
3. .github/workflows/*.yml: each workflow that runs on pull_request, with the reusable workflows
   that its jobs call. A job counts when it names a touched project, or names no project (a root
   job). Each `run:` step of such a job is one command, with its file:line, job, cwd and env. A step
   that needs CI context (`${{ }}`, secrets, OIDC, push-only) is listed as excluded, with the reason.
4. Formal tools, when <project>/formal/ exists at the ready-branch tip: `lake build` for each Lean
   project, `formal_tlc.py check` for each TLC cfg, and `formal_tlc.py vectors --check` for each
   vectors file that formal_tlc.py wrote (its header names the spec, the cfg and the stop rule).

The user approves the command list once, before first use (`--approve`). The approval holds the
digest of the commands; a changed list needs a new yes. `--approve --project NAME` approves only the
commands that run in that project's folder; the gate then refuses every other command. probe, close, trim and review call `gate()`:
each verifier and setup command must match an approved command (the same positional words in the
same order, extra words after them, in the same folder or below), or a formal tool.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import ctx as context  # noqa: E402
import miniyaml  # noqa: E402
import repoinfo  # noqa: E402
import tm  # noqa: E402

SCHEMA = "understando.ci/1"
SHELL_META = re.compile(r"[$|&;<>`()*?\[\]{}~]")
FORMAL_TOOLS = ("lake", "lean", "java")
UNDERSTANDO_SCRIPTS = ("formal_tlc.py", "formal_run.py", "formal_lean.py", "formal_witness.py")


def extract(repo: Path, ref: str, prefix: str, dest: Path) -> Path:
    """Write the tree `prefix` at `ref` into `dest` with git archive: no checkout, no hooks, no filters."""
    import subprocess
    import tarfile
    dest.mkdir(parents=True, exist_ok=True)
    arc = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", ref, "--", prefix], capture_output=True)
    if arc.returncode:
        raise RuntimeError(f"git archive {ref} {prefix} failed: {arc.stderr.decode(errors='ignore').strip()}")
    import io
    with tarfile.open(fileobj=io.BytesIO(arc.stdout)) as tar:
        tar.extractall(dest, filter="data")
    return dest


def show(repo: Path, ref: str, path: str) -> str | None:
    try:
        return repoinfo.git(repo, "show", f"{ref}:{path}")
    except RuntimeError:
        return None


def ls(repo: Path, ref: str, prefix: str) -> list[str]:
    try:
        out = repoinfo.git(repo, "ls-tree", "-r", "--name-only", ref, "--", prefix)
    except RuntimeError:
        return []
    return [p for p in out.splitlines() if p]


# ---- AGENTS.md ---------------------------------------------------------------------------------

def agents_md(repo: Path, ref: str, paths: list[str]) -> dict:
    rules, cmds = [], []
    for p in paths:
        text = show(repo, ref, p)
        if text is None:
            continue
        fence = False
        for n, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith("```"):
                fence = not fence
                continue
            if fence and line.strip() and not line.strip().startswith("#"):
                cmds.append({"source": f"{p}:{n}", "command": line.strip()})
            elif re.search(r"(?i)\bCI profile\b|\breviewed CI\b|\broot workflow\b", line):
                rules.append({"source": f"{p}:{n}", "text": line.strip()[:240]})
    return {"rules": rules, "commands": cmds}


# ---- catalog -----------------------------------------------------------------------------------

def catalog(repo: Path, ref: str) -> list[dict] | None:
    text = show(repo, ref, "catalog.toml")
    if text is None:
        return None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None
    return [{"name": p["name"], "path": p["path"].rstrip("/")} for p in data.get("projects", []) if p.get("name") and p.get("path")]


def outside_paths(projects: list[dict] | None, changed: list[str] | None) -> list[str]:
    if projects is None or changed is None:
        return []
    return [p for p in changed if not (p.endswith(".md") or p.startswith("docs/"))
            and not any(p == x["path"] or p.startswith(x["path"] + "/") for x in projects)]


def by_project(projects: list[dict] | None, changed: list[str] | None) -> dict[str, int]:
    out: dict[str, int] = {}
    for path in changed or []:
        owner = next((x["name"] for x in projects or [] if path == x["path"] or path.startswith(x["path"] + "/")), None)
        if owner:
            out[owner] = out.get(owner, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def project_of(projects: list[dict] | None, cwd: str) -> str | None:
    cwd = cwd.strip("./")
    return next((x["name"] for x in projects or [] if cwd == x["path"] or cwd.startswith(x["path"] + "/")), None)


def touched(projects: list[dict] | None, changed: list[str] | None) -> tuple[list[str], str]:
    if projects is None:
        return [], "no catalog: the whole repo is one project"
    names = [p["name"] for p in projects]
    if changed is None:
        return names, "the diff is unknown: fail open to every project"
    hit, outside = set(), []
    for path in changed:
        if path.endswith(".md") or path.startswith("docs/"):
            continue
        owner = next((p["name"] for p in projects if path == p["path"] or path.startswith(p["path"] + "/")), None)
        if owner:
            hit.add(owner)
        else:
            outside.append(path)
    if outside:
        return names, f"{len(outside)} changed paths are outside every project (for example {outside[0]}): fail open to every project"
    return sorted(hit), "the changed paths are inside these projects"


# ---- workflows ---------------------------------------------------------------------------------

def triggers(wf: dict) -> list[str]:
    on = wf.get("on") if "on" in wf else wf.get(True)
    if isinstance(on, str):
        return [on]
    if isinstance(on, list):
        return [str(x) for x in on]
    return [str(k) for k in (on or {})]


def literal_env(*blocks) -> tuple[dict, list[str]]:
    env, ci_only = {}, []
    for b in blocks:
        for k, v in (b or {}).items():
            if v is not None and "${{" in str(v):
                ci_only.append(str(k))
            else:
                env[str(k)] = str(v if v is not None else "")
    return env, ci_only


def split_run(text: str) -> list[tuple[int, dict]]:
    """A run block as commands: (line offset, {argv} or {shell}). Simple lines become argv lists;
    a line with shell syntax stays a bash line. `set -e...` lines go."""
    out, buf, start = [], "", 0
    for k, line in enumerate(text.splitlines()):
        s = line.strip()
        if not buf:
            start = k
        if s.endswith("\\"):
            buf += s[:-1] + " "
            continue
        buf += s
        cmd, buf = buf.strip(), ""
        if not cmd or cmd.startswith("#") or re.fullmatch(r"set -[euxo pipefail]+", cmd):
            continue
        try:
            toks = shlex.split(cmd)
        except ValueError:
            toks = []
        if toks and not any(SHELL_META.search(t) for t in toks) and "=" not in toks[0]:
            out.append((start, {"argv": toks}))
        else:
            out.append((start, {"shell": cmd}))
    if any("shell" in c for _, c in out):
        # Shell syntax in one line (a loop, a heredoc, a pipe) binds the lines: keep the block whole.
        body = "\n".join(line for line in text.splitlines() if line.strip()).strip()
        return [(out[0][0], {"shell": body})] if out else []
    return out


def jobs_of(repo: Path, ref: str) -> list[dict]:
    """Every concrete job that runs on a pull request: (workflow file, job id, job, caller)."""
    files = [p for p in ls(repo, ref, ".github/workflows") if p.endswith((".yml", ".yaml"))]
    wfs = {}
    for f in files:
        try:
            wfs[f] = miniyaml.load(show(repo, ref, f) or "") or {}
        except ValueError as exc:
            wfs[f] = {"_error": str(exc)}
    out = []
    for f, wf in wfs.items():
        if "pull_request" not in triggers(wf):
            continue
        for jid, job in (wf.get("jobs") or {}).items():
            uses = str(job.get("uses") or "")
            if uses.startswith("./.github/workflows/"):
                callee = uses[2:]
                for cid, cjob in ((wfs.get(callee) or {}).get("jobs") or {}).items():
                    out.append({"file": callee, "id": str(cid), "job": cjob, "wf": wfs[callee],
                                "caller": {"file": f, "id": str(jid), "job": job}})
            else:
                out.append({"file": f, "id": str(jid), "job": job, "wf": wf, "caller": None})
    return out


def project_names(text: str, names: list[str]) -> set[str]:
    return {n for n in names if re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-]*/)", text)}


def job_text(j: dict) -> str:
    parts = [j["id"], str(j["job"].get("if") or ""), str(j["job"].get("name") or "")]
    d = ((j["job"].get("defaults") or {}).get("run") or {}).get("working-directory")
    if d:
        parts.append(str(d))
    if j["caller"]:
        parts += [j["caller"]["id"], str(j["caller"]["job"].get("if") or ""), j["file"]]
    return " ".join(parts)


def excluded_job(j: dict) -> str | None:
    job, caller = j["job"], j["caller"] or {}
    cond = " ".join(str(x) for x in (job.get("if"), (caller.get("job") or {}).get("if")) if x)
    if re.search(r"event_name\s*==\s*'push'|refs/heads/main", cond):
        return "it runs only on a push to main"
    perms = [job.get("permissions"), (caller.get("job") or {}).get("permissions"), j["wf"].get("permissions")]
    if any(isinstance(p, dict) and str(p.get("id-token")) == "write" for p in perms):
        return "it needs OIDC (id-token: write)"
    if (caller.get("job") or {}).get("secrets"):
        return "it needs repository secrets"
    return None


def commands_at(repo: Path, ref: str, names: list[str], hit: list[str]) -> tuple[list[dict], list[dict]]:
    included, excluded = [], []
    for j in jobs_of(repo, ref):
        named = project_names(job_text(j), names) if names else set()
        if named and not named & set(hit):
            continue
        scope = sorted(named) or ["root"]
        why_job = excluded_job(j)
        job = j["job"]
        cwd_default = ((job.get("defaults") or {}).get("run") or {}).get("working-directory") or "."
        for step in job.get("steps") or []:
            run = step.get("run")
            if run is None:
                continue
            env, ci_only = literal_env(j["wf"].get("env"), job.get("env"), step.get("env"))
            cwd = str(step.get("working-directory") or cwd_default)
            why_step = why_job
            if not why_step and step.get("if") and re.search(r"event_name\s*==\s*'pull_request'", str(step["if"])) is None:
                why_step = f"its step condition needs CI context: {step['if']}"
            for off, cmd in split_run(str(run)):
                text = cmd.get("shell") or " ".join(cmd["argv"])
                why = why_step
                if not why and "${{" in text:
                    why = "the command uses a CI expression (${{ }})"
                if not why and ci_only and any(re.search(rf"\${{?{re.escape(v)}\b", text) for v in ci_only):
                    why = "the command reads an env variable that only CI sets: " + ", ".join(ci_only)
                if not why and "GITHUB_" in text:
                    why = "the command needs a GitHub runner variable"
                if not why and re.fullmatch(r"echo .*", text):
                    why = "an echo, not a check"
                row = {"workflow": j["file"], "job": j["id"], "step": str(step.get("name") or ""), "scope": scope,
                       "source": f"{j['file']}:{run.line + off}", "cwd": cwd, "env": env, **cmd}
                if j["caller"]:
                    row["called_by"] = f"{j['caller']['file']}:{j['caller']['id']}"
                if why:
                    excluded.append({**row, "excluded": why})
                else:
                    included.append(row)
    return included, excluded


# ---- formal tools ------------------------------------------------------------------------------

def vectors_header(text: str) -> dict | None:
    first = text.split('"vectors": [', 1)[0]
    try:
        head = json.loads(first.rstrip().rstrip(",") + "}")
    except json.JSONDecodeError:
        return None
    return head if {"spec", "cfg", "done"} <= set(head) else None


def formal_commands(repo: Path, ref: str, projects: list[str]) -> list[dict]:
    out = []
    tlc = str(tm.ROOT / "scripts" / "formal_tlc.py")
    for proj in projects:
        files = ls(repo, ref, f"{proj}/formal" if proj != "." else "formal")
        for f in files:
            d, name = f.rsplit("/", 1)
            if name in ("lakefile.toml", "lakefile.lean"):
                out.append({"kind": "formal", "tool": "lean", "source": f"understando formal tool: {f} at {ref[:10]}",
                            "cwd": d, "argv": ["lake", "build"], "scope": [proj]})
            if name.endswith(".cfg"):
                specs = sorted((x for x in files if x.endswith(".tla") and x.rsplit("/", 1)[0] == d
                                and name.startswith(x.rsplit("/", 1)[1][:-4])), key=len, reverse=True)
                if specs and "Vectors" not in name:
                    out.append({"kind": "formal", "tool": "tlc", "source": f"understando formal tool: {f} at {ref[:10]}", "cwd": d,
                                "argv": ["python3", tlc, "check", "--spec", specs[0].rsplit("/", 1)[1], "--cfg", name], "scope": [proj]})
            if "vectors" in name and name.endswith(".json"):
                head = vectors_header(show(repo, ref, f) or "")
                if head:
                    text = show(repo, ref, f) or ""
                    first = next((json.loads(line.rstrip(",")) for line in text.splitlines()[1:] if line.startswith("{")), {})
                    argv = ["python3", tlc, "vectors", "--spec", head["spec"], "--cfg", head["cfg"]]
                    for cond in head["done"]:
                        argv += ["--done", cond]
                    for k in sorted(first):
                        argv += ["--keep", k]
                    out.append({"kind": "formal", "tool": "tlc-vectors", "source": f"understando formal tool: {f} at {ref[:10]}", "cwd": d,
                                "argv": argv + ["--out", name, "--check"], "scope": [proj], "generates": f})
    return out


# ---- the profile -------------------------------------------------------------------------------

def digest(cmds: list[dict]) -> str:
    key = [(c.get("argv") or c.get("shell"), c["cwd"], c.get("env", {})) for c in cmds]
    return "sha256:" + hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()


def changed_paths(repo: Path, base: str | None, head: str) -> list[str] | None:
    if not base:
        return None
    try:
        mb = repoinfo.git(repo, "merge-base", base, head)
        return [p for p in repoinfo.git(repo, "diff", "--name-only", "--no-renames", mb, head).splitlines() if p]
    except RuntimeError:
        return None


def build(repo: Path, head: str, base: str | None, ready: str | None, pr: str | None) -> dict:
    projects = catalog(repo, head)
    names = [p["name"] for p in projects or []]
    changed = changed_paths(repo, base, head)
    hit, why = touched(projects, changed)
    paths = {p["name"]: p["path"] for p in projects or []}
    md = agents_md(repo, head, ["AGENTS.md"] + [f"{paths[h]}/AGENTS.md" for h in hit])
    included, excluded = commands_at(repo, head, names, hit)
    base_cmds = []
    if base:
        try:
            base_cmds, _ = commands_at(repo, repoinfo.git(repo, "merge-base", base, head), names, hit)
        except RuntimeError:
            base_cmds = []
    seen = {(json.dumps(c.get("argv") or c.get("shell")), c["cwd"]) for c in base_cmds}
    for c in included:
        c["kind"] = "ci"
        c["reviewed_at_base"] = (json.dumps(c.get("argv") or c.get("shell")), c["cwd"]) in seen
    formal = formal_commands(repo, ready or head, [paths[h] for h in hit] if projects else ["."])
    cmds = included + formal
    for i, c in enumerate(cmds, 1):
        c["id"] = f"CI{i:02d}"
        c["project"] = project_of(projects, c["cwd"])
    for row in md["commands"]:
        row["in_profile"] = any(row["command"] == (c.get("shell") or " ".join(c.get("argv", []))) for c in included)
    return {"schema": SCHEMA, "repo": repoinfo.slug(repoinfo.origin_url(repo)) or repo.name, "pr": pr, "head": head, "base": base,
            "ready": ready, "generated_at": tm.now(), "catalog": {"projects": names, "touched": hit, "why": why,
                                                                   "changed": len(changed) if changed is not None else None,
                                                                   "by_project": by_project(projects, changed),
                                                                   "outside": outside_paths(projects, changed)},
            "agents_md": md, "commands": cmds, "excluded": excluded, "digest": digest(cmds), "approval": None}


def load(run: Path | None) -> dict | None:
    p = run / "ci.json" if run else None
    return json.loads(p.read_text(encoding="utf-8")) if p and p.is_file() else None


def save(run: Path, prof: dict) -> None:
    old = load(run)
    if old and old.get("approval"):
        prof["approval"] = old["approval"]
        if not approved(prof):
            prof["approval"] = None
    (run / "ci.json").write_text(json.dumps(prof, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def project_commands(prof: dict, name: str) -> list[dict]:
    return [c for c in prof.get("commands", []) if c.get("project") == name]


def approved_commands(prof: dict | None) -> list[dict]:
    """The commands that the user approved: all of them, or the commands of the approved projects.
    A changed list needs a new yes: the digest of the approved commands must match."""
    a = (prof or {}).get("approval")
    if not a:
        return []
    if a.get("projects"):
        cmds = [c for n in a["projects"] for c in project_commands(prof, n)]
        return cmds if cmds and digest(cmds) == a.get("digest") else []
    return list(prof["commands"]) if a.get("digest") == prof.get("digest") else []


def approved(prof: dict | None) -> bool:
    return bool(approved_commands(prof))


def fully_approved(prof: dict | None) -> bool:
    a = (prof or {}).get("approval") or {}
    return approved(prof) and not a.get("projects")


def approve(prof: dict, project: str | None, by: str) -> str:
    """Record the user's yes in prof. It returns a one-line report."""
    if project:
        cmds = project_commands(prof, project)
        if not cmds:
            known = sorted({c["project"] for c in prof["commands"] if c.get("project")})
            tm.fail(f"ci --approve --project {project}: no command runs in that project. Projects: {', '.join(known) or 'none'}", 2)
        prof["approval"] = {"digest": digest(cmds), "projects": [project], "commands": [c["id"] for c in cmds], "at": tm.now(), "by": by}
        import prompt
        return f"ci: approved {prompt.n_of(len(cmds), 'command')} of {project} ({prof['approval']['digest'][:19]}); every other command stays refused"
    prof["approval"] = {"digest": prof["digest"], "at": tm.now(), "by": by}
    return f"ci: approved {len(prof['commands'])} commands ({prof['digest'][:19]})"


# ---- the question ------------------------------------------------------------------------------

def why_line(prof: dict) -> str:
    cat = prof["catalog"]
    out = cat.get("outside") or []
    kinds = []
    for name, test in (("workflow files", lambda p: p.startswith(".github/")), ("root tests", lambda p: p.startswith("tests/")),
                       ("root scripts", lambda p: p.startswith("scripts/"))):
        if any(test(p) for p in out):
            kinds.append(name)
    if any(not p.startswith((".github/", "tests/", "scripts/")) for p in out):
        kinds.append("other root files")
    if out:
        return f"the PR touches {' and '.join(kinds)} outside every project"
    if cat.get("touched"):
        return f"the PR touches {', '.join(cat['touched'])}"
    return "the repo has no project catalog"


def main_project(prof: dict) -> str | None:
    """The project that owns the most changed paths and has commands in the profile."""
    for name in (prof["catalog"].get("by_project") or {}):
        if project_commands(prof, name):
            return name
    return None


def question(prof: dict, then: str | None = None) -> dict:
    """The CI approval as one question. `then` says what runs after a yes."""
    import prompt
    n = len(prof["commands"])
    after = f" Then {then}." if then else ""
    opts = [prompt.option(f"Approve all {n}" if n > 1 else "Approve it", f"Records your yes for {prompt.n_of(n, 'command')}, and only these may run.{after}", "understando ci --approve"),
            prompt.option("Show the list", "Prints each command with its workflow file and line.", "understando ci")]
    mp = main_project(prof)
    if mp and len({c.get("project") for c in prof["commands"]}) > 1:
        k = len(project_commands(prof, mp))
        opts.append(prompt.option(f"Approve only {mp}", f"Records your yes for {prompt.n_of(k, 'command')} of {mp}. The other {n - k} stay refused.", f"understando ci --approve --project {mp}"))
    return prompt.make([f"CI: you must approve {prompt.n_of(n, 'command')} from your workflows, because {why_line(prof)}."],
                       "Approve the CI profile?", opts)


# ---- the gate ----------------------------------------------------------------------------------

def positional(argv: list[str]) -> list[str]:
    return [t for t in argv if not t.startswith("-")]


def allowed_by(prof: dict, argv: list[str], cwd: str) -> dict | None:
    """The profile command that allows `argv` in `cwd`, else None."""
    cwd = cwd.strip("./") or "."
    pos = positional(argv)
    for c in prof.get("commands", []):
        ccwd = c["cwd"].strip("./") or "."
        if not (ccwd == "." or cwd == ccwd or cwd.startswith(ccwd + "/")):
            continue
        cargv = c.get("argv") or []
        if c.get("kind") == "formal":
            if pos[:1] == positional(cargv)[:1] and (pos[:1] == ["lake"] or Path(pos[1] if len(pos) > 1 else "").name == Path(cargv[1]).name):
                return c
            continue
        if cargv:
            want = positional(cargv)
            if pos[:len(want)] == want:
                return c
        elif c.get("shell") and " ".join(argv) == c["shell"]:
            return c
    if pos and (Path(pos[-1] if pos[0] == "python3" and len(pos) > 1 else pos[0]).name in UNDERSTANDO_SCRIPTS
                or (pos[0] == "python3" and len(pos) > 1 and Path(pos[1]).name in UNDERSTANDO_SCRIPTS)):
        return {"id": "understando", "source": "an understando formal helper"}
    if argv[:3] == ["npx", "--no-install", "@spolu/cc-check@0.2.0"]:
        return {"id": "cc-check", "source": "the understando contract checker"}
    return None


def gate(c: context.Ctx, data: dict, verifier_ids: set[str] | None = None) -> tuple[str | None, list[str]]:
    """(refusal, notes). No ci.json: a note, no refusal (the run predates the CI profile).
    An unapproved profile, or a command outside it, is a refusal."""
    prof = load(c.run)
    if not prof:
        return None, ["no CI profile (ci.json) in the run folder: run `understando ci` and show it to the user"]
    prof = {**prof, "commands": approved_commands(prof)}
    if not prof["commands"]:
        return ("refuse: the CI profile is not approved. Show `understando ci` to the user, and after a clear yes "
                "the user runs `understando ci --approve`."), []
    bad = []
    for step in data.get("setup", []):
        if not allowed_by(prof, step["argv"], step.get("cwd", ".")):
            bad.append(f"setup {' '.join(step['argv'])}")
    for v in data["verifiers"]:
        if "command" not in v or (verifier_ids and v["id"] not in verifier_ids):
            continue
        if not allowed_by(prof, v["command"]["argv"], v["command"].get("cwd", ".")):
            bad.append(f"{v['id']} {' '.join(v['command']['argv'])}")
    if bad:
        return ("refuse: these commands are not in the approved CI profile (ci.json): " + "; ".join(bad)
                + ". Take commands only from the repo's reviewed CI. Fix the trust map, or run `understando ci` again "
                "and ask the user to approve the new list."), []
    return None, []


# ---- the verb ----------------------------------------------------------------------------------

def text_of(prof: dict) -> str:
    cat = prof["catalog"]
    lines = [f"CI profile for {prof['repo']}#{prof['pr']} at {prof['head'][:10]}"
             + (f" (formal tools at {prof['ready'][:10]})" if prof.get("ready") else ""),
             f"projects touched: {', '.join(cat['touched']) or 'the whole repo'} ({cat['why']})"]
    for r in prof["agents_md"]["rules"]:
        lines.append(f"  rule {r['source']}: {r['text']}")
    lines.append("commands (only these run):")
    for c in prof["commands"]:
        cmd = c.get("shell") or " ".join(c["argv"])
        tag = c.get("kind") if c.get("kind") == "formal" else ("" if c.get("reviewed_at_base") else "new in this PR")
        lines.append(f"  {c['id']} [{c['cwd']}] {cmd}   <- {c['source']}" + (f" ({c.get('job')})" if c.get("job") else "") + (f" {tag}" if tag else ""))
    if prof["excluded"]:
        lines.append("excluded:")
        lines += [f"  {c['source']} {c.get('shell') or ' '.join(c['argv'])}: {c['excluded']}" for c in prof["excluded"]]
    doc_only = [r for r in prof["agents_md"]["commands"] if not r["in_profile"]]
    if doc_only:
        lines.append("named only in AGENTS.md (data; never run unless a workflow runs it too):")
        lines += [f"  {r['source']}: {r['command']}" for r in doc_only]
    if approved(prof):
        a = prof["approval"]
        lines.append(f"approved by the user at {a['at']}" + (f", only for {', '.join(a['projects'])}." if a.get("projects") else "."))
    else:
        lines.append("NOT APPROVED. Show this list to the user. After a clear yes, the user runs `understando ci --approve`.")
    return "\n".join(lines)


def resolve_refs(c: context.Ctx, head: str | None, base: str | None, ready: str | None) -> tuple[Path, str, str | None, str | None]:
    repo = c.repo or repoinfo.repo_root(Path.cwd())
    if not repo:
        tm.fail("ci: no repo. Run it in a clone of the reviewed repo, or pass --repo", 2)
    data = c.data() or {}
    info = None
    if not head and c.pr:
        info = repoinfo.gh_pr(c.pr, repoinfo.slug(repoinfo.origin_url(repo)))
    head = head or (info or {}).get("headRefOid") or data.get("head")
    if not head:
        tm.fail("ci: no PR head. Pass --head SHA, or install gh", 2)
    if not base:
        bname = (info or {}).get("baseRefName")
        base = (repoinfo.rev(repo, f"origin/{bname}") if bname else None) or data.get("base") or repoinfo.rev(repo, "origin/main")
    cfg = config.load(repoinfo.repo_name(repo))
    branch = cfg["ready_branch"].format(pr=c.pr) if c.pr else None
    if not ready and branch:
        ready = repoinfo.rev(repo, f"origin/{branch}") or repoinfo.rev(repo, branch)
    return repo, head, base, ready


def main(c: context.Ctx, argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="understando ci", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--head")
    ap.add_argument("--base")
    ap.add_argument("--ready")
    ap.add_argument("--approve", action="store_true", help="the user only: record the yes for the current list")
    ap.add_argument("--project", help="with --approve: approve only the commands of this catalog project")
    ap.add_argument("--question", action="store_true", help="print the approval as one question, not the list")
    ap.add_argument("--check-argv", nargs=argparse.REMAINDER)
    args = ap.parse_args(argv)
    run = c.need_run()
    if args.approve:
        prof = load(run)
        if not prof:
            tm.fail("ci --approve: no ci.json yet; run `understando ci` and show it to the user first", 2)
        line = approve(prof, args.project, "user")
        (run / "ci.json").write_text(json.dumps(prof, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        import journal
        journal.append(c.journal, "decision", line, c.repo, evidence=str(run / "ci.json"), result=prof["approval"]["digest"])
        print(line)
        return 0
    if args.check_argv is not None:
        prof = load(run)
        hit = allowed_by(prof or {}, args.check_argv, ".") if prof else None
        ok = hit and allowed_by({"commands": approved_commands(prof)}, args.check_argv, ".")
        print((f"allowed by {hit['id']} ({hit['source']}), " + ("approved" if ok else "not approved")) if hit else "not in the CI profile")
        return 0 if hit else 1
    repo, head, base, ready = resolve_refs(c, args.head, args.base, args.ready)
    prof = build(repo, head, base, ready, c.pr)
    run.mkdir(parents=True, exist_ok=True)
    save(run, prof)
    prof = load(run)
    if args.question:
        import prompt
        q = question(prof)
        context.emit(c, {"prompt": q}, prompt.render(q))
        return 0
    context.emit(c, prof, text_of(prof) + f"\nwrote {run / 'ci.json'}")
    return 0
