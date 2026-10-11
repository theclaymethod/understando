"""The intent ledger: runs/<repo>/<pr>/journal.jsonl, append-only, local only.

`understando note` is its only writer. Each row: ts, kind, what, and optional why, evidence,
result, claims and source. The columns match the decision log of the show-me-your-work skill
(what, why, evidence, result), and `understando note --export-tsv` writes that TSV.

Each text field is redacted before it is written: key-like strings, bearer tokens, key=value
pairs with a secret name, and each value from the .env files of the repo, the working folder and
$UNDERSTANDO_ENV_FILES. The journal stays out of git (.gitignore) and out of the reviewed repo.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tm  # noqa: E402

KINDS = ("prompt", "decision", "verifier-choice", "waiver", "result", "invariant")
DEDUPE_SECONDS = 120
MASK = "[REDACTED]"

KEY_PATTERNS = [
    re.compile(r"\bsk-(?:ant-|proj-|svcacct-)?[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
]
BEARER = re.compile(r"(?i)\b(bearer|token)\s+[A-Za-z0-9._~+/=-]{12,}")
ASSIGN = re.compile(r"(?i)\b([A-Z0-9_]*(?:api[_-]?key|secret|token|password|passwd|credential)[A-Z0-9_]*)(\s*[=:]\s*)(['\"]?)[^\s'\"]+\3")


def env_values(extra_dirs: list[Path]) -> list[str]:
    """Values from .env files, longest first. They are read only to mask them, never printed."""
    files: list[Path] = []
    for d in extra_dirs + [Path.cwd()]:
        files += sorted(d.glob(".env*")) if d.is_dir() else []
    files += [Path(p) for p in os.environ.get("UNDERSTANDO_ENV_FILES", "").split(os.pathsep) if p]
    values = set()
    for f in files:
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            m = re.match(r"\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*(.*)$", line)
            if m:
                value = m.group(1).strip().strip("'\"")
                if len(value) >= 8:
                    values.add(value)
    return sorted(values, key=len, reverse=True)


def redact(text: str, env: list[str]) -> str:
    for value in env:
        text = text.replace(value, MASK)
    for pattern in KEY_PATTERNS:
        text = pattern.sub(MASK, text)
    text = BEARER.sub(lambda m: f"{m.group(1)} {MASK}", text)
    return ASSIGN.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)


def what(row: dict) -> str:
    return row.get("what") or row.get("text") or ""


TSV_COLUMNS = ("ts", "phase", "decision", "why", "evidence", "result")


def export_tsv(rows: list[dict], dest: Path) -> int:
    """The show-me-your-work decision log: one row per journal row, the kind as the phase."""
    def cell(v) -> str:
        text = " ".join(str(v if not isinstance(v, list) else ", ".join(map(str, v))).split())
        return "'" + text if text[:1] in ("=", "+", "-", "@") else text
    lines = ["\t".join(TSV_COLUMNS)]
    for r in rows:
        lines.append("\t".join(cell(x) for x in (r.get("ts", ""), r.get("kind", ""), what(r), r.get("why", ""), r.get("evidence", ""), r.get("result", ""))))
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(rows)


def read(path: Path | None) -> list[dict]:
    if not path or not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def append(path: Path, kind: str, text: str, repo: Path | None = None, **fields) -> dict | None:
    """Write one redacted row. A prompt that repeats the last prompt within two minutes is a
    duplicate (the hook and the agent both noted it), so the second one is skipped."""
    if kind not in KINDS:
        tm.fail(f"note: unknown kind {kind!r}; use one of {', '.join(KINDS)}", 2)
    env = env_values([repo] if repo else [])
    row = {"ts": tm.now(), "kind": kind, "what": redact(text, env)}
    for key, value in fields.items():
        if value in (None, "", []):
            continue
        row[key] = redact(value, env) if isinstance(value, str) else value
    if kind == "prompt":
        last = next((r for r in reversed(read(path)) if r.get("kind") == "prompt"), None)
        if last and what(last) == row["what"]:
            try:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(last["ts"])
            except (KeyError, ValueError):
                age = timedelta(days=1)
            if age < timedelta(seconds=DEDUPE_SECONDS):
                return None
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row
