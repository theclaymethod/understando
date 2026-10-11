"""Fast, offline-safe, never-fatal probes of the external tools (java, cc-check).

Presence comes from the filesystem and PATH first. A tool runs only to check that it works, with
stdin closed and a 5 second limit. npx runs with `--no-install` and npm_config_offline=true, and
it does not run at all while the network is known to be down ($UNDERSTANDO_OFFLINE). A probe that
fails or times out is never fatal: it becomes a note, which doctor shows as a mention.
Definite results are cached in ~/.understando/toolprobe.json for one day; `doctor --refresh`
probes again. Standard library only.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

TIMEOUT = 5
TTL = 24 * 3600
CC_PKG = "@spolu/cc-check@0.2.0"
JAVA_HOMES = ("/opt/homebrew/opt/openjdk", "/usr/local/opt/openjdk")
_REFRESH = [False]


def refresh(on: bool = True) -> None:
    _REFRESH[0] = on


def _home() -> Path:
    return Path(os.environ.get("UNDERSTANDO_HOME") or Path.home() / ".understando")


def _cache_path() -> Path:
    return _home() / "toolprobe.json"


def _load() -> dict:
    try:
        d = json.loads(_cache_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _cached(name: str):
    """(hit, value). A hit is a definite result younger than the TTL."""
    if _REFRESH[0]:
        return False, None
    e = _load().get(name)
    if isinstance(e, dict) and time.time() - float(e.get("at", 0)) < TTL:
        return True, e.get("value")
    return False, None


def _store(name: str, value) -> None:
    try:
        d = _load()
        d[name] = {"value": value, "at": time.time()}
        _cache_path().parent.mkdir(parents=True, exist_ok=True)
        _cache_path().write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def run_probe(argv: list[str], env: dict | None = None) -> tuple[bool | None, str]:
    """(ok, note). ok is None when the probe could not finish (timeout or OS error)."""
    try:
        out = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=TIMEOUT,
                             env={**os.environ, **(env or {})})
    except subprocess.TimeoutExpired:
        return None, "timed out"
    except OSError as e:
        return None, f"could not run ({type(e).__name__})"
    return out.returncode == 0, ""


# ---- java ---------------------------------------------------------------------------------------

def java_bin() -> str | None:
    """A java that runs: $UNDERSTANDO_JAVA, $JAVA_HOME/bin/java, Homebrew's openjdk, java on PATH.
    The macOS stub /usr/bin/java prints an install prompt and fails, so it never counts."""
    hit, val = _cached("java")
    if hit and (val is None or Path(val).is_file()):
        return val
    cands = [os.environ.get("UNDERSTANDO_JAVA")]
    if os.environ.get("JAVA_HOME"):
        cands.append(str(Path(os.environ["JAVA_HOME"]) / "bin" / "java"))
    cands += [f"{h}/bin/java" for h in JAVA_HOMES] + [shutil.which("java")]
    unfinished = False
    for c in cands:
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            ok, _ = run_probe([c, "-version"])
            if ok:
                _store("java", c)
                return c
            unfinished = unfinished or ok is None
    if not unfinished:
        _store("java", None)
    return None


# ---- cc-check -----------------------------------------------------------------------------------

def _cc_on_disk() -> str | None:
    """cc-check from the filesystem: a bin on PATH, the npx cache, or a global npm root."""
    if shutil.which("cc-check"):
        return "cc-check"
    caches = [os.environ.get("npm_config_cache"), str(Path.home() / ".npm")]
    pats = [f"{c}/_npx/*/node_modules/@spolu/cc-check/package.json" for c in caches if c]
    pats += [f"{r}/@spolu/cc-check/package.json" for r in
             ("/usr/local/lib/node_modules", "/opt/homebrew/lib/node_modules", str(Path.home() / ".npm-global/lib/node_modules"))]
    for p in pats:
        for hit in glob.glob(p):
            try:
                if json.loads(Path(hit).read_text(encoding="utf-8")).get("version") == "0.2.0":
                    return f"npx {CC_PKG}"
            except (OSError, ValueError):
                continue
    return None


def cc_check() -> tuple[str | None, str]:
    """(command or None, note). A note means the probe did not finish: the tool is not checked."""
    hit, val = _cached("cc-check")
    if hit:
        return val, ""
    found = _cc_on_disk()
    if found:
        _store("cc-check", found)
        return found, ""
    if not shutil.which("npx"):
        _store("cc-check", None)
        return None, ""
    if os.environ.get("UNDERSTANDO_OFFLINE"):
        return None, "not checked (offline)"
    ok, note = run_probe(["npx", "--no-install", CC_PKG, "--help"], {"DO_NOT_TRACK": "1", "npm_config_offline": "true"})
    if ok is None:
        return None, f"not checked ({note})"
    val = f"npx {CC_PKG}" if ok else None
    _store("cc-check", val)
    return val, ""
