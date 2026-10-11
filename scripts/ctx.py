"""The context that every understando verb shares: the mode state, the run folder, the repo and the PR.

Standard library only. The mode state file is $UNDERSTANDO_HOME/mode.json (default ~/.understando).
A verb finds its run folder in this order: --run, then the active run in the mode state, then
runs/<repo folder name>/<pr> when --repo and --pr are given.
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
        run_p = Path(os.environ.get("UNDERSTANDO_RUNS") or ROOT / "runs") / repoinfo.repo_name(repo_p) / pr_s
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


def tool_status() -> dict:
    """Which formal and contract tools are on this machine. understando never installs them."""
    def on_path(name: str) -> str | None:
        return shutil.which(name)

    jar = os.environ.get("TLA2TOOLS_JAR")
    if not jar:
        for d in (Path.home() / ".tla", Path.home() / "lib", Path("/usr/local/lib"), Path("/opt/homebrew/lib")):
            if (d / "tla2tools.jar").is_file():
                jar = str(d / "tla2tools.jar")
                break
    cc = None
    if on_path("npx"):
        probe = subprocess.run(["npx", "--no-install", "@spolu/cc-check@0.2.0", "--help"], capture_output=True, text=True,
                               env={**os.environ, "DO_NOT_TRACK": "1"}, timeout=60)
        cc = "npx @spolu/cc-check@0.2.0" if probe.returncode == 0 else None
    java = on_path("java")
    if java and subprocess.run(["java", "-version"], capture_output=True).returncode != 0:
        java = None  # the macOS stub prints an install prompt and fails
    return {"lean": on_path("lean"), "lake": on_path("lake"), "java": java, "tla2tools": jar,
            "apalache": on_path("apalache-mc") or on_path("apalache"), "cc-check": cc}


def emit(ctx: Ctx, payload: dict, text: str) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False) if ctx.json else text)
