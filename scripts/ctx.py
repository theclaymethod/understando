"""The context that every understando verb shares: the mode state, the run folder, the repo and the PR.

Standard library only. The mode state file is $UNDERSTANDO_HOME/mode.json (default ~/.understando).
A verb finds its run folder in this order: --run, then the active run in the mode state, then
<runs root>/<repo name>/<pr> when --repo and --pr are given. The runs root is ~/.understando/runs
(scripts/config.py: UNDERSTANDO_RUNS, runs_root in ~/.understando/config.toml, or runs_dir in the
per-repo config override it). Run state is local: refuse_run_write() keeps it out of every git repo.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import tm  # noqa: E402

ROOT = tm.ROOT
COMMANDS = ROOT / "commands.json"


def home() -> Path:
    return Path(os.environ.get("UNDERSTANDO_HOME") or Path.home() / ".understando")


def mode_path() -> Path:
    return home() / "mode.json"


def load_mode() -> dict:
    p = mode_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"on": False, "error": f"{p} is not valid JSON"}
    return {"on": False}


def save_mode(state: dict) -> None:
    p = mode_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def commands() -> dict:
    return json.loads(COMMANDS.read_text(encoding="utf-8"))


@dataclass
class Ctx:
    run: Path | None
    repo: Path | None
    pr: str | None
    json: bool
    explicit_repo: bool = False

    @property
    def map(self) -> Path | None:
        return self.run / "trust-map.json" if self.run else None

    @property
    def journal(self) -> Path | None:
        return self.run / "journal.jsonl" if self.run else None

    def data(self) -> dict | None:
        return tm.load(self.map) if self.map and self.map.is_file() else None

    def need_run(self) -> Path:
        if not self.run:
            tm.fail("no run folder: pass --run DIR, or --repo and --pr, or turn the mode on with `understando mode on --run DIR`", 2)
        return self.run

    def need_map(self) -> dict:
        self.need_run()
        if not self.map.is_file():
            tm.fail(f"no trust map at {self.map}: run `understando map` first (commands/map.md)", 2)
        return tm.load(self.map)

    def need_repo(self) -> Path:
        if not self.repo:
            tm.fail("no repo: pass --repo <local clone of the reviewed repo>, or turn the mode on with --repo", 2)
        return self.repo


def resolve(run: str | None, repo: str | None, pr: str | None, as_json: bool) -> Ctx:
    state = load_mode() if load_mode().get("on") else {}
    repo_p = Path(repo).expanduser().resolve() if repo else (Path(state["repo"]) if state.get("repo") else None)
    pr_s = str(pr) if pr else (str(state["pr"]) if state.get("pr") else None)
    import repoinfo
    if not repo_p and pr_s and not run and not state.get("run"):
        repo_p = repoinfo.repo_root(Path.cwd())
    if run:
        run_p = Path(run).expanduser().resolve()
    elif state.get("run") and not (pr and state.get("pr") and str(state["pr"]) != str(pr)):
        run_p = Path(state["run"])
    elif repo_p and pr_s:
        import config
        run_p = config.run_dir(repoinfo.repo_name(repo_p), pr_s)
    else:
        run_p = None
    if run_p and not pr_s and (run_p / "trust-map.json").is_file():
        pr_s = str(tm.load(run_p / "trust-map.json").get("pr"))
    return Ctx(run_p, repo_p, pr_s, as_json, bool(repo))


def git(repo: Path, *args: str, check: bool = True) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and out.returncode != 0:
        tm.fail(f"git {' '.join(args[:3])} failed: {out.stderr.strip()}", 1)
    return out.stdout.strip()


JAVA_HOMES = ("/opt/homebrew/opt/openjdk", "/usr/local/opt/openjdk")


def java_bin() -> str | None:
    """A java that runs, without a PATH edit (see toolprobe.java_bin). A formal step passes the
    returned path to its command explicitly."""
    import toolprobe
    return toolprobe.java_bin()


def tla2tools_jar() -> str | None:
    """$UNDERSTANDO_TLA2TOOLS, $TLA2TOOLS_JAR, then ~/.understando/tools/tla2tools.jar."""
    for c in (os.environ.get("UNDERSTANDO_TLA2TOOLS"), os.environ.get("TLA2TOOLS_JAR"),
              str(home() / "tools" / "tla2tools.jar"), str(Path.home() / ".understando" / "tools" / "tla2tools.jar")):
        if c and Path(c).is_file():
            return c
    return None


def tool_status() -> dict:
    """Which formal and contract tools are on this machine. understando never installs them."""
    def on_path(name: str) -> str | None:
        return shutil.which(name)

    import toolprobe
    cc, cc_note = toolprobe.cc_check()
    return {"lean": on_path("lean"), "lake": on_path("lake"), "java": java_bin(), "tla2tools": tla2tools_jar(),
            "apalache": on_path("apalache-mc") or on_path("apalache"), "cc-check": cc,
            "probe_notes": {"cc-check": cc_note} if cc_note else {}}


# ---- the run-state guard -----------------------------------------------------------------------

def git_toplevel(path: Path) -> Path | None:
    """The work tree of the git repo that holds `path` (or its nearest folder that exists), else None."""
    p = Path(path).expanduser().resolve()
    while not p.exists() and p != p.parent:
        p = p.parent
    if p.is_file():
        p = p.parent
    out = subprocess.run(["git", "-C", str(p), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(out.stdout.strip()).resolve() if out.returncode == 0 and out.stdout.strip() else None


def refuse_run_write(run: Path | None, repo: Path | None = None) -> str | None:
    """None when a verb may write run output into `run`; else the refusal text.

    Run output never goes into the reviewed repo's working tree, nor into any git repo (also
    understando's own checkout). The ready branch worktree and the publish branch are written
    through git, not as run output, so this guard does not cover them. Stable for other verbs."""
    if not run:
        return None
    r = Path(run).expanduser().resolve()
    if repo:
        rr = Path(repo).expanduser().resolve()
        if r == rr or rr in r.parents:
            return (f"refuse: the run folder {r} is inside the reviewed repo {rr}. Run state stays out of it; "
                    "use the default runs root (~/.understando/runs) or --run DIR outside every git repo.")
    top = git_toplevel(r)
    if top:
        return (f"refuse: the run folder {r} is inside the git repo {top}. Run state is local and never in a git repo; "
                "use the default runs root (~/.understando/runs) or --run DIR outside every git repo.")
    return None


def emit(ctx: Ctx, payload: dict, text: str) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False) if ctx.json else text)
