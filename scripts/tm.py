"""Shared helpers for the understando scripts: load, save and validate a trust map.

Standard library only. The schema in ../schema/trust-map.schema.json is the source of truth.
`validate` applies the subset of JSON Schema that file uses, then the cross-reference rules:

- every id is unique across claims, verifiers and controls;
- every verifier backs only claims that exist;
- every control names a verifier that exists;
- a verifier has a command, recorded evidence or a mechanical check;
- a mechanical check names a pattern (grep) or an expected net line count (net-lines);
- with `promises=True` (validate.py, verdicts.py, explain.py): each claim is in exactly one
  promise, and each promise names only claims that exist;
- a verifier judged by a model names its family and its context, and kind `model` is guess tier;
- a verifier on ladder rung 4 or 5 has a `formal` block (its proof or model, and its conformance link).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "trust-map.schema.json"

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\b(\s*[=:]\s*)\S+"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
]


# The verification ladder. A rung counts for a claim only after a control shows that the check can fail.
KIND_LADDER = {"e2e": 1, "integration": 1, "unit": 1, "golden": 1, "parity": 1, "eval": 1, "measurement": 1,
               "property": 2, "fuzz": 2, "type-pin": 3, "contract": 3, "contract-format": 3, "boundary": 3,
               "static": 3, "tla": 4, "lean": 5}
LADDER_NAMES = {1: "e2e or integration test", 2: "property or fuzz test", 3: "types, contracts or static rules",
                4: "model checking", 5: "proof with conformance"}


def ladder(v: dict) -> int | None:
    """The ladder rung of a verifier: its own `ladder`, else the rung of its kind."""
    return v.get("ladder") or KIND_LADDER.get(v["kind"])


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def redact(text: str) -> str:
    """Mask values that look like credentials before output goes into a trust map."""
    text = _SECRET_PATTERNS[0].sub("sk-REDACTED", text)
    text = _SECRET_PATTERNS[1].sub(lambda m: f"{m.group(1)}{m.group(2)}REDACTED", text)
    return _SECRET_PATTERNS[2].sub("gh_REDACTED", text)


def load(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save(data: dict, path: str | Path) -> None:
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    tmp.replace(path)


def _type_ok(value, expected) -> bool:
    names = expected if isinstance(expected, list) else [expected]
    for name in names:
        if name == "null" and value is None:
            return True
        if name == "boolean" and isinstance(value, bool):
            return True
        if name == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if name == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if name == "string" and isinstance(value, str):
            return True
        if name == "array" and isinstance(value, list):
            return True
        if name == "object" and isinstance(value, dict):
            return True
    return False


def _resolve(schema: dict, root: dict) -> dict:
    while "$ref" in schema:
        ref = schema["$ref"]
        assert ref.startswith("#/"), ref
        node = root
        for part in ref[2:].split("/"):
            node = node[part]
        schema = node
    return schema


def _check(value, schema: dict, root: dict, where: str, errors: list[str]) -> None:
    schema = _resolve(schema, root)
    if "type" in schema and not _type_ok(value, schema["type"]):
        errors.append(f"{where}: expected {schema['type']}, got {type(value).__name__}")
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{where}: empty string")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{where}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{where}: {value} < {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{where}: {value} > {schema['maximum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{where}: needs at least {schema['minItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
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


def validate(data: dict, promises: bool = True) -> list[str]:
    root = load(SCHEMA_PATH)
    errors: list[str] = []
    _check(data, root, root, "$", errors)
    if errors:
        return errors
    seen: set[str] = set()
    for section in ("claims", "verifiers", "controls"):
        for item in data[section]:
            if item["id"] in seen:
                errors.append(f"{section}: duplicate id {item['id']}")
            seen.add(item["id"])
    claim_ids = {c["id"] for c in data["claims"]}
    verifier_ids = {v["id"] for v in data["verifiers"]}
    for v in data["verifiers"]:
        for cid in v["claims"]:
            if cid not in claim_ids:
                errors.append(f"verifier {v['id']}: unknown claim {cid}")
        if not {"command", "recorded", "mechanical"} & set(v):
            errors.append(f"verifier {v['id']}: needs a command, recorded evidence or a mechanical check")
        m = v.get("mechanical")
        if m and m["op"].startswith("grep") and "pattern" not in m:
            errors.append(f"verifier {v['id']}: a grep check needs a pattern")
        if m and m["op"] == "net-lines" and "expect" not in m:
            errors.append(f"verifier {v['id']}: a net-lines check needs expect")
        ind = v["independence"]
        if ind["by"] == "model" and ("family" not in ind or "context" not in ind):
            errors.append(f"verifier {v['id']}: a model verifier names its family and context")
        if v["kind"] == "model" and v["tier"] != "guess":
            errors.append(f"verifier {v['id']}: a model verifier is guess tier")
        if ladder(v) and ladder(v) >= 4 and "formal" not in v:
            errors.append(f"verifier {v['id']}: a tier {ladder(v)} verifier needs a formal block with its conformance link")
    invariant_ids = {i["id"] for i in data.get("invariants", [])}
    for c in data["claims"]:
        if c.get("invariant") and c["invariant"] not in invariant_ids:
            errors.append(f"claim {c['id']}: unknown invariant {c['invariant']}")
    for k in data["controls"]:
        if k["verifier"] not in verifier_ids:
            errors.append(f"control {k['id']}: unknown verifier {k['verifier']}")
        for e in k["edits"]:
            if e["op"] == "replace" and ("find" not in e or "replace" not in e):
                errors.append(f"control {k['id']}: replace needs find and replace")
            if e["op"] == "append" and "text" not in e:
                errors.append(f"control {k['id']}: append needs text")
            if e["op"] in ("delete-line", "invert-condition", "replace-with", "drop-allowlist-row") and not ({"symbol", "match"} & set(e)):
                errors.append(f"control {k['id']}: {e['op']} needs a symbol or a match")
            if e["op"] == "replace-with" and ("with" not in e or "match" not in e):
                errors.append(f"control {k['id']}: replace-with needs match and with")
    for c in data["claims"]:
        for ref in c.get("code", []):
            if ({"symbol", "match"} & set(ref)) and ({"start", "end"} & set(ref)):
                errors.append(f"claim {c['id']}: a code ref is an anchor or a line range, not both")
            if ({"part"} & set(ref)) and "symbol" not in ref:
                errors.append(f"claim {c['id']}: part needs a symbol")
    if promises:
        errors += promise_errors(data)
    return errors


def promise_errors(data: dict) -> list[str]:
    """Each claim is in exactly one promise, and each promise names only claims that exist."""
    groups = data.get("promises") or []
    if not groups:
        return ["promises: the map has no promises; write three to six (commands/map.md)"]
    errors = []
    claim_ids = {c["id"] for c in data["claims"]}
    seen: dict[str, list[str]] = {}
    for p in groups:
        for cid in p["claims"]:
            if cid not in claim_ids:
                errors.append(f"promise {p['id']}: unknown claim {cid}")
            seen.setdefault(cid, []).append(p["id"])
    for c in data["claims"]:
        where = seen.get(c["id"], [])
        if not where:
            errors.append(f"claim {c['id']}: in no promise")
        elif len(where) > 1:
            errors.append(f"claim {c['id']}: in {len(where)} promises ({', '.join(where)})")
    if not 3 <= len(groups) <= 6:
        errors.append(f"promises: {len(groups)} promises; write three to six")
    return errors


def fail(message: str, code: int = 2) -> None:
    print(message, file=sys.stderr)
    sys.exit(code)
