"""The evidence store and the context that every verb shares.

Standard library only. The store is one JSON file, <run>/verify.json, in the shape of
schema/verify.schema.json: the features, the invariants, the claims, the checks, the controls,
the mutation runs and their results. Each code ref in it is an anchor (scripts/coderef.py).

The run folder is --run DIR, else <runs root>/<repo name>/<app>. The app is --app NAME, else the
one app folder under <runs root>/<repo name>/, else the repo name. The runs root is
$UNDERSTANDO_RUNS, else $UNDERSTANDO_HOME/runs (default ~/.understando/runs). A run folder is
never inside a git repo (refuse_run_write).

Each command that a verb runs is the user's call: confirm() shows the commands once and runs
them only with --yes, on each invocation. No approval is stored.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "verify.schema.json"
SCHEMA = "understando.verify/1"
# The verification ladder. A rung counts only after a control shows that the check can fail.
LADDER = {"e2e": 1, "integration": 1, "eval": 1, "property": 2, "fuzz": 2, "type": 3, "contract": 3,
          "static": 3, "tla": 4, "lean": 5}
LADDER_NAMES = {1: "e2e or integration test", 2: "property or fuzz test", 3: "types, contracts or static rules",
                4: "model check (TLA+)", 5: "proof with conformance (Lean)"}
PREFIX = {"features": "F", "invariants": "I", "claims": "C", "checks": "V", "controls": "K", "mutation": "M"}

_SECRET = [re.compile(r"sk-[A-Za-z0-9_-]{16,}"), re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\b(\s*[=:]\s*)\S+"),
           re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")]


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stamp() -> str:
    return now().replace(":", "").replace("+0000", "Z")


def redact(text: str) -> str:
    text = _SECRET[0].sub("sk-REDACTED", text)
    text = _SECRET[1].sub(lambda m: f"{m.group(1)}{m.group(2)}REDACTED", text)
    return _SECRET[2].sub("gh_REDACTED", text)


def fail(message: str, code: int = 2):
    print(message, file=sys.stderr)
    sys.exit(code)


def ladder(check: dict) -> int | None:
    return check.get("ladder") or LADDER.get(check.get("kind", ""))


def home() -> Path:
    return Path(os.environ.get("UNDERSTANDO_HOME") or Path.home() / ".understando")


def runs_root() -> Path:
    return Path(os.environ.get("UNDERSTANDO_RUNS") or home() / "runs")


def git(repo: Path, *args: str, check: bool = True) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])} failed: {out.stderr.strip()}")
    return out.stdout.strip()


# ---- the context -------------------------------------------------------------------------------

@dataclass
class Ctx:
    run: Path | None
    repo: Path | None
    app: str | None
    json: bool
    yes: bool = False

    @property
    def store(self) -> Path | None:
        return self.run / "verify.json" if self.run else None

    def need_repo(self) -> Path:
        if not self.repo:
            fail("no repo: run understando in a clone, or pass --repo DIR", 2)
        return self.repo

    def need_run(self) -> Path:
        if not self.run:
            fail("no run folder: pass --run DIR, or --repo DIR (and --app NAME)", 2)
        refusal = refuse_run_write(self.run)
        if refusal:
            fail(refusal, 1)
        self.run.mkdir(parents=True, exist_ok=True)
        return self.run

    def data(self) -> dict | None:
        return load(self.store) if self.store and self.store.is_file() else None

    def need_data(self) -> dict:
        self.need_run()
        if not self.store.is_file():
            fail(f"no evidence store at {self.store}: run `understando create` or `understando discover` first", 2)
        return load(self.store)

    def open_data(self) -> dict:
        """The store, or a new one for the repo."""
        self.need_run()
        if self.store.is_file():
            return load(self.store)
        repo = self.need_repo()
        import repoinfo
        return new(repoinfo.slug(repoinfo.origin_url(repo)) or repoinfo.repo_name(repo), self.app or repoinfo.repo_name(repo),
                   git(repo, "rev-parse", "HEAD"))

    def save(self, data: dict) -> None:
        save(data, self.store)


def resolve(run: str | None, repo: str | None, app: str | None, as_json: bool, yes: bool) -> Ctx:
    import repoinfo
    repo_p = Path(repo).expanduser().resolve() if repo else repoinfo.repo_root(Path.cwd())
    if run:
        run_p = Path(run).expanduser().resolve()
        if not app and (run_p / "verify.json").is_file():
            app = load(run_p / "verify.json").get("app")
    elif repo_p:
        base = runs_root() / repoinfo.repo_name(repo_p)
        if not app:
            apps = sorted(p.parent.name for p in base.glob("*/verify.json")) if base.is_dir() else []
            app = apps[0] if len(apps) == 1 else repoinfo.repo_name(repo_p)
        run_p = base / app
    else:
        run_p = None
    return Ctx(run_p, repo_p, app, as_json, yes)


def git_toplevel(path: Path) -> Path | None:
    p = Path(path).expanduser().resolve()
    while not p.exists() and p != p.parent:
        p = p.parent
    if p.is_file():
        p = p.parent
    out = subprocess.run(["git", "-C", str(p), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(out.stdout.strip()).resolve() if out.returncode == 0 and out.stdout.strip() else None


def refuse_run_write(run: Path | None) -> str | None:
    """None when run output may go into `run`. Run output never goes into a git repo."""
    if not run:
        return None
    r = Path(run).expanduser().resolve()
    top = git_toplevel(r)
    if top:
        return (f"refuse: the run folder {r} is inside the git repo {top}. Run state is local and never in a git repo; "
                "use the default runs root (~/.understando/runs) or --run DIR outside every git repo.")
    return None


def emit(c: Ctx, payload: dict, text: str) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False) if c.json else text)


def confirm(c: Ctx, what: str, commands: list[list[str] | str], cwd: str | None = None) -> bool:
    """Show the commands that a step runs, once. True only with --yes on this invocation."""
    if not commands:
        return True
    if c.yes:
        return True
    shown = list(dict.fromkeys(" ".join(x) if isinstance(x, (list, tuple)) else x for x in commands))
    lines = [f"{what} runs these commands{' in ' + cwd if cwd else ''}:"] + [f"  {x}" for x in shown]
    lines += ["They run in a scratch copy of the repo, never in your checkout.",
              "Run them? Repeat the same command with --yes. understando stores no approval: it asks again next time."]
    if c.json:
        print(json.dumps({"confirm": {"what": what, "commands": shown}}, indent=2))
    else:
        print("\n".join(lines))
    return False


# ---- load, save and validate -------------------------------------------------------------------

def new(repo: str, app: str, head: str) -> dict:
    return {"schema": SCHEMA, "repo": repo, "app": app, "head": head, "features": [], "invariants": [],
            "claims": [], "checks": [], "controls": [], "mutation": []}


def load(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save(data: dict, path: str | Path) -> None:
    errors = validate(data)
    if errors:
        fail("refuse to save an invalid evidence store:\n" + "\n".join(errors[:20]), 1)
    data["updated_at"] = now()
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def next_id(data: dict, section: str) -> str:
    prefix = PREFIX[section]
    n = max([int(x["id"][len(prefix):]) for x in data.get(section, []) if x["id"][len(prefix):].isdigit()] + [0]) + 1
    return f"{prefix}{n}"


def find(data: dict, section: str, item_id: str | None) -> dict | None:
    return next((x for x in data.get(section, []) if x["id"] == item_id), None)


def need(data: dict, section: str, item_id: str | None) -> dict:
    item = find(data, section, item_id)
    if not item:
        fail(f"no {section[:-1] if section.endswith('s') else section} {item_id}", 2)
    return item


def _type_ok(value, expected) -> bool:
    for name in expected if isinstance(expected, list) else [expected]:
        if (name == "null" and value is None) or (name == "boolean" and isinstance(value, bool)) \
                or (name == "integer" and isinstance(value, int) and not isinstance(value, bool)) \
                or (name == "number" and isinstance(value, (int, float)) and not isinstance(value, bool)) \
                or (name == "string" and isinstance(value, str)) or (name == "array" and isinstance(value, list)) \
                or (name == "object" and isinstance(value, dict)):
            return True
    return False


def _check(value, schema: dict, root: dict, where: str, errors: list[str]) -> None:
    while "$ref" in schema:
        node = root
        for part in schema["$ref"][2:].split("/"):
            node = node[part]
        schema = node
    if "type" in schema and not _type_ok(value, schema["type"]):
        errors.append(f"{where}: expected {schema['type']}, got {type(value).__name__}")
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        errors.append(f"{where}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{where}: needs at least {schema['minItems']} items")
        for i, item in enumerate(value):
            if "items" in schema:
                _check(item, schema["items"], root, f"{where}[{i}]", errors)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{where}: missing {key!r}")
        for key, item in value.items():
            if key in props:
                _check(item, props[key], root, f"{where}.{key}", errors)
            elif schema.get("additionalProperties", True) is False:
                errors.append(f"{where}: unknown key {key!r}")


def validate(data: dict) -> list[str]:
    root = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors: list[str] = []
    _check(data, root, root, "$", errors)
    if errors:
        return errors
    ids = {s: {x["id"] for x in data.get(s, [])} for s in PREFIX}
    for s in PREFIX:
        if len(ids[s]) != len(data.get(s, [])):
            errors.append(f"{s}: duplicate id")
    for s in ("invariants", "claims", "checks", "mutation"):
        for x in data.get(s, []):
            if x.get("feature") and x["feature"] not in ids["features"]:
                errors.append(f"{s[:-1]} {x['id']}: unknown feature {x['feature']}")
    for cl in data.get("claims", []):
        for i in cl.get("invariants", []):
            if i not in ids["invariants"]:
                errors.append(f"claim {cl['id']}: unknown invariant {i}")
        for p in [cl] + cl.get("parts", []):
            for v in p.get("checks", []):
                if v not in ids["checks"]:
                    errors.append(f"claim {cl['id']}: unknown check {v}")
    for k in data.get("controls", []):
        if k["check"] not in ids["checks"]:
            errors.append(f"control {k['id']}: unknown check {k['check']}")
    for v in data.get("checks", []):
        if (ladder(v) or 0) >= 4 and "formal" not in v:
            errors.append(f"check {v['id']}: a rung {ladder(v)} check needs a formal block with its conformance link")
    return errors
