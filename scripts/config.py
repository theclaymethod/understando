"""The per-repo config: <runs root>/<repo name>/understando.toml. It never lives in the reviewed repo.

    understando setup --repo [DIR] [--answers FILE]   write the file (asks each item on a terminal)
    python3 scripts/config.py deny-globs --repo DIR   the read-deny globs for the learn sandbox

Keys (all optional; the defaults are below):

    schema = "understando.repo/1"
    repo = "Owner/name"
    budget_usd = 0                      # paid steps need a shown cost and a clear yes from the user
    ready_branch = "understando/{pr}-ready"
    worktree_root = ".claude/worktrees" # relative to the repo root; the worktree is understando-{pr}-ready
    secret_paths = ["**/.env*"]         # globs; understando never reads a matching file
    [[protected_paths]]                 # findings only: understando never edits a matching file
    path = "src/x/"  owner = "X team"  reason = "..."
    [llm]
    key_source = "env-file"             # the only allowed source
    env_file = "/abs/path/.env"         # read only by the key loader, never by a verb or an agent
    env_var = "OPENAI_API_KEY"
    require_key_for = ["judiciary"]     # a command that names one of these words never runs with the key unset
    [deferred_owners]
    "A5-q2" = "loop design"

A secret path wins over every other rule, except `llm.env_file`: the key loader passes that one
file to a command by path. It never reads the value into understando. Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tm  # noqa: E402

SCHEMA = "understando.repo/1"
FORBIDDEN_KEY_SOURCES = ("keychain", "op", "1password", "inherited", "login", "personal")
DEFAULTS = {"schema": SCHEMA, "budget_usd": 0, "ready_branch": "understando/{pr}-ready",
            "worktree_root": ".claude/worktrees", "secret_paths": ["**/.env*"], "protected_paths": [],
            "llm": {}, "deferred_owners": {}}


def runs_root() -> Path:
    return Path(os.environ.get("UNDERSTANDO_RUNS") or tm.ROOT / "runs")


def path_for(repo_name: str) -> Path:
    return runs_root() / repo_name / "understando.toml"


def load(repo_name: str | None) -> dict:
    """The config with defaults filled in. `present` says whether the file exists."""
    cfg = json.loads(json.dumps(DEFAULTS))
    if not repo_name:
        return {**cfg, "present": False, "path": None}
    p = path_for(repo_name)
    if p.is_file():
        try:
            raw = tomllib.loads(p.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            return {**cfg, "present": True, "path": str(p), "error": f"{p}: {exc}"}
        cfg.update(raw)
        return {**cfg, "present": True, "path": str(p)}
    return {**cfg, "present": False, "path": str(p)}


# ---- globs ------------------------------------------------------------------------------------

@lru_cache(maxsize=256)
def _glob_re(pattern: str) -> re.Pattern:
    """A path glob: `**/` is any number of folders, `*` stays inside one folder, a trailing `/`
    matches everything below that folder."""
    if pattern.endswith("/"):
        pattern += "**"
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out + r"\Z")


def matches(pattern: str, rel: str) -> bool:
    rel = rel.lstrip("./") if rel.startswith("./") else rel
    return bool(_glob_re(pattern).match(rel))


def for_repo(repo) -> dict:
    """The config of a local clone, found by its origin name."""
    import repoinfo
    return load(repoinfo.repo_name(Path(repo))) if repo else load(None)


def readable(cfg: dict, paths):
    """The paths that are not secret, in order."""
    return [p for p in paths if not secret(cfg, p)]


def secret(cfg: dict, rel: str) -> str | None:
    """The secret glob that `rel` matches, else None."""
    return next((g for g in cfg.get("secret_paths", []) if matches(g, rel)), None)


def protected(cfg: dict, rel: str) -> dict | None:
    """The protected entry that covers `rel`, else None."""
    return next((p for p in cfg.get("protected_paths", []) if matches(p["path"], rel)), None)


def refuse_edit(cfg: dict, rel: str) -> str | None:
    """None when understando may write `rel` on the ready branch; else the refusal text."""
    s = secret(cfg, rel)
    if s:
        return f"refuse: {rel} is a secret path ({s}). understando never reads or writes it."
    p = protected(cfg, rel)
    if p:
        return (f"refuse: {rel} is protected (owner {p.get('owner', 'unknown')}: {p.get('reason', 'no reason given')}). "
                "Report the finding to the owner. Do not edit the file.")
    return None


def pathspec_excludes(cfg: dict) -> list[str]:
    """git pathspecs that keep a secret path out of git grep, git diff and git ls-files."""
    return [f":(exclude,glob){g if not g.endswith('/') else g + '**'}" for g in cfg.get("secret_paths", [])]


def deny_globs(cfg: dict, repo_root: Path) -> list[str]:
    """Absolute globs for a sandbox read-deny list: each secret path under the repo root."""
    return [str(repo_root / g) for g in cfg.get("secret_paths", [])]


# ---- the key rule ------------------------------------------------------------------------------

def needs_key(cfg: dict, argv: list[str]) -> bool:
    words = [w.lower() for w in (cfg.get("llm") or {}).get("require_key_for", [])]
    text = " ".join(argv).lower()
    return any(w in text for w in words)


def key_names_present(env_file: Path, var: str) -> bool:
    """True when the env file assigns a non-empty value to `var`. It reads names only: the
    value never leaves this function, and nothing prints it."""
    if not env_file.is_file():
        return False
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = re.match(rf"\s*(?:export\s+)?{re.escape(var)}\s*=\s*(.*)$", line)
        if m and m.group(1).strip().strip("'\""):
            return True
    return False


def key_wrapper(cfg: dict, out_dir: Path, base_env_file: str | None) -> Path:
    """A bash env file that sources the verifier env file (when one is set), then exports only
    `env_var` from `llm.env_file`, and exits 97 when the key is unset. understando never reads the value."""
    llm = cfg.get("llm") or {}
    var, src = llm["env_var"], llm["env_file"]
    lines = ["# written by understando: the key rule of understando.toml"]
    if base_env_file:
        lines.append(f'source "{base_env_file}"')
    lines += [f"unset {var}",
              f'{var}="$(sed -n -E \'s/^[[:space:]]*(export[[:space:]]+)?{var}[[:space:]]*=[[:space:]]*//p\' "{src}" | tail -1 | tr -d "\\"\'")"',
              f'[ -n "${var}" ] || {{ echo "understando: {var} is not set in {src}; the command does not run without it" >&2; exit 97; }}',
              f"export {var}"]
    p = out_dir / "key-env.sh"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def drop_inherited_key(cfg: dict) -> list[str]:
    """Remove the key variable from this process, so no command inherits it from the caller."""
    var = (cfg.get("llm") or {}).get("env_var")
    names = [var] if var else []
    dropped = [n for n in names if os.environ.pop(n, None) is not None]
    return dropped


# ---- checks for doctor -------------------------------------------------------------------------

def findings(cfg: dict, repo_root: Path | None) -> list[dict]:
    out: list[dict] = []

    def add(id_: str, severity: str, summary: str, fix: str, verb: str | None = None) -> None:
        out.append({"id": id_, "severity": severity, "summary": summary, "fix": fix, **({"verb": verb} if verb else {})})

    if not cfg.get("present"):
        add("config-missing", "route", f"No per-repo config at {cfg.get('path')}.", "Write it with the user.", "setup --repo")
        return out
    if cfg.get("error"):
        add("config-invalid", "route", cfg["error"], "Fix the TOML.", "setup --repo")
        return out
    if cfg.get("schema") != SCHEMA:
        add("config-schema", "mention", f"The config schema is {cfg.get('schema')!r}, not {SCHEMA!r}.", "Write the file again.")
    if not isinstance(cfg.get("budget_usd"), (int, float)) or cfg["budget_usd"] < 0:
        add("config-budget", "route", "budget_usd must be a number, 0 or more.", "Set budget_usd.", "setup --repo")
    for p in cfg.get("protected_paths", []):
        if not p.get("path") or not p.get("owner"):
            add("config-protected", "route", f"A protected path needs a path and an owner: {p}.", "Add the owner.", "setup --repo")
    if "{pr}" not in str(cfg.get("ready_branch", "")):
        add("config-ready-branch", "route", "ready_branch must hold {pr}.", "Set ready_branch.", "setup --repo")
    llm = cfg.get("llm") or {}
    if llm:
        src = str(llm.get("key_source", ""))
        if src != "env-file" or any(w in src.lower() for w in FORBIDDEN_KEY_SOURCES):
            add("config-key-source", "route", f"llm.key_source is {src!r}. The only allowed source is an env file.",
                "Set key_source = \"env-file\" with env_file and env_var.", "setup --repo")
        elif not llm.get("env_file") or not llm.get("env_var"):
            add("config-key-source", "route", "llm.key_source is env-file, but env_file or env_var is missing.", "Add both.", "setup --repo")
        else:
            ef = Path(llm["env_file"])
            if str(llm["env_file"]).startswith("op://") or not ef.is_absolute():
                add("config-key-file", "route", "llm.env_file must be an absolute path to a file, not an op reference.", "Fix it.", "setup --repo")
            elif not key_names_present(ef, llm["env_var"]):
                add("config-key-unset", "mention", f"{ef} does not set {llm['env_var']}. A command that needs the key does not run.",
                    "Ask the user to set the key in that file.")
    if repo_root:
        for p in cfg.get("protected_paths", []):
            base = p.get("path", "").rstrip("/").split("*")[0]
            if base and not (repo_root / base).exists():
                add("config-protected-gone", "mention", f"The protected path {p['path']} does not exist in {repo_root}.",
                    "Update protected_paths, or keep it when the path only exists on another branch.")
    return out


# ---- setup --repo ------------------------------------------------------------------------------

def _toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def render(cfg: dict) -> str:
    lines = [f"# understando per-repo config for {cfg.get('repo', '')}. understando never writes this file into the reviewed repo.",
             f"schema = {_toml_str(SCHEMA)}"]
    if cfg.get("repo"):
        lines.append(f"repo = {_toml_str(cfg['repo'])}")
    lines += [f"budget_usd = {cfg.get('budget_usd', 0)}",
              f"ready_branch = {_toml_str(cfg.get('ready_branch', DEFAULTS['ready_branch']))}",
              f"worktree_root = {_toml_str(cfg.get('worktree_root', DEFAULTS['worktree_root']))}",
              "# understando never reads a file that matches one of these globs.",
              "secret_paths = [" + ", ".join(_toml_str(g) for g in cfg.get("secret_paths", [])) + "]", ""]
    for p in cfg.get("protected_paths", []):
        lines += ["# understando reports findings here and never edits these files.", "[[protected_paths]]",
                  f"path = {_toml_str(p['path'])}", f"owner = {_toml_str(p['owner'])}", f"reason = {_toml_str(p.get('reason', ''))}", ""]
    llm = cfg.get("llm") or {}
    if llm:
        lines += ["# The only key source: one env file and one variable. Never the keychain, an op reference,",
                  "# an inherited variable or a personal login. A command that names a word in require_key_for",
                  "# never runs with the key unset, and it is a paid step: it needs a shown cost and a yes.",
                  "[llm]", f"key_source = {_toml_str(llm.get('key_source', 'env-file'))}",
                  f"env_file = {_toml_str(llm['env_file'])}", f"env_var = {_toml_str(llm['env_var'])}",
                  "require_key_for = [" + ", ".join(_toml_str(w) for w in llm.get("require_key_for", [])) + "]", ""]
    owners = cfg.get("deferred_owners") or {}
    lines.append("# The owner of each deferred invariant question, when the trust map does not name one.")
    lines.append("[deferred_owners]")
    lines += [f"{_toml_str(k)} = {_toml_str(v)}" for k, v in owners.items()]
    return "\n".join(lines) + "\n"


def setup_repo(repo_name: str, repo_slug: str | None, answers: str | None) -> int:
    """Write understando.toml. With --answers, the file holds the user's answers as JSON. On a
    terminal, each item is a question. Without either, it prints the questions and writes nothing."""
    dest = path_for(repo_name)
    cur = load(repo_name)
    if answers:
        spec = json.loads(Path(answers).read_text(encoding="utf-8"))
    elif sys.stdin.isatty():
        def ask(q: str, default: str = "") -> str:
            got = input(f"{q}{f' [{default}]' if default else ''}: ").strip()
            return got or default
        spec = {"repo": ask("owner/repo", repo_slug or cur.get("repo", "")),
                "budget_usd": float(ask("budget in USD for paid steps (0 means none)", str(cur.get("budget_usd", 0)))),
                "secret_paths": [g.strip() for g in ask("secret globs, comma-separated", ",".join(cur["secret_paths"])).split(",") if g.strip()],
                "protected_paths": [], "deferred_owners": dict(cur.get("deferred_owners") or {})}
        while True:
            p = ask("a protected path (Enter to stop)")
            if not p:
                break
            spec["protected_paths"].append({"path": p, "owner": ask("  owner"), "reason": ask("  reason")})
        ef = ask("the env file that holds the model key (Enter for none)")
        if ef:
            spec["llm"] = {"key_source": "env-file", "env_file": ef, "env_var": ask("  variable name", "OPENAI_API_KEY"),
                           "require_key_for": [w.strip() for w in ask("  words of commands that need the key, comma-separated").split(",") if w.strip()]}
    else:
        print("setup --repo: no terminal and no --answers FILE. Ask the user these items, then pass the answers as JSON:\n"
              "  repo, budget_usd, secret_paths, protected_paths [{path, owner, reason}],\n"
              "  llm {key_source: env-file, env_file, env_var, require_key_for}, deferred_owners {id: owner},\n"
              "  ready_branch, worktree_root")
        return 2
    cfg = {**{k: v for k, v in cur.items() if k not in ("present", "path", "error")}, **spec}
    cfg.setdefault("repo", repo_slug)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render(cfg), encoding="utf-8")
    bad = [f for f in findings(load(repo_name), None) if f["severity"] == "route"]
    print(f"wrote {dest}")
    for f in bad:
        print(f"  {f['id']}: {f['summary']}")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="config.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("deny-globs")
    d.add_argument("--repo", required=True)
    d.add_argument("--name")
    s = sub.add_parser("show")
    s.add_argument("--name", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "deny-globs":
        import repoinfo
        root = Path(args.repo).resolve()
        name = args.name or repoinfo.repo_name(root)
        print("\n".join(deny_globs(load(name), root)))
        return 0
    print(json.dumps(load(args.name), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
