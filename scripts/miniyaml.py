"""A small YAML reader for GitHub workflow files. Standard library only.

It reads block mappings, block sequences, plain and quoted scalars, block scalars (| and >),
and simple flow lists. Each scalar is a `S` (a str) that knows its 1-based line. Anchors, tags
and multi-document files are not supported: a workflow does not need them.
"""

from __future__ import annotations

import re
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)


class S(str):
    line: int = 0

    def __new__(cls, value: str, line: int):
        s = super().__new__(cls, value)
        s.line = line
        return s


def _strip_comment(text: str) -> str:
    out, q = [], None
    for i, ch in enumerate(text):
        if q:
            if ch == q:
                q = None
        elif ch in "'\"" and (i == 0 or text[i - 1] in " :[,"):
            q = ch
        elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _scalar(text: str, line: int):
    t = text.strip()
    if t.startswith("[") and t.endswith("]"):
        return [_scalar(x, line) for x in t[1:-1].split(",") if x.strip()]
    if t == "{}":
        return {}
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
        t = t[1:-1].replace("''", "'") if t[0] == "'" else t[1:-1].replace('\\"', '"')
    return S(t, line)


_KEY = re.compile(r"""^("(?:[^"\\]|\\.)*"|'[^']*'|[^:#'"][^:]*?)\s*:(?:\s+(.*)|\s*)$""")


def load(text: str):
    raw = text.splitlines()
    rows = []
    for n, line in enumerate(raw, 1):
        body = line.rstrip()
        if not body.strip() or body.strip().startswith("#") or body.strip() in ("---", "..."):
            continue
        rows.append([n, len(body) - len(body.lstrip(" ")), body.strip()])
    value, _ = _block(rows, 0, rows[0][1] if rows else 0, raw)
    return value


def _block(rows, i, indent, raw):
    if i >= len(rows):
        return None, i
    if rows[i][2] == "-" or rows[i][2].startswith("- "):
        return _seq(rows, i, indent, raw)
    return _map(rows, i, indent, raw)


def _block_scalar(rows, i, indent, raw, style):
    """Lines after rows[i] that are more indented, or blank. Returns (S, next row index)."""
    start = rows[i][0]
    j, body, first = start, [], None
    while j < len(raw):
        line = raw[j]
        if line.strip() and len(line) - len(line.lstrip(" ")) <= indent:
            break
        body.append((j + 1, line))
        j += 1
    while body and not body[-1][1].strip():
        body.pop()
    lines = [b for _, b in body]
    cut = min((len(b) - len(b.lstrip(" ")) for b in lines if b.strip()), default=0)
    first = next((n for n, b in body if b.strip()), start)
    text = "\n".join(b[cut:] for b in lines)
    if style.startswith(">"):
        text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    k = i + 1
    while k < len(rows) and rows[k][0] <= j:
        k += 1
    return S(text, first), k


def _value(rows, i, indent, raw, rest, line):
    rest = _strip_comment(rest or "")
    if rest in ("|", "|-", "|+", ">", ">-", ">+"):
        return _block_scalar(rows, i, indent, raw, rest)
    if rest:
        return _scalar(rest, line), i + 1
    if i + 1 < len(rows) and (rows[i + 1][1] > indent or (rows[i + 1][1] == indent and rows[i + 1][2].startswith("- "))):
        return _block(rows, i + 1, rows[i + 1][1], raw)
    return None, i + 1


def _map(rows, i, indent, raw):
    out: dict = {}
    while i < len(rows) and rows[i][1] == indent and not rows[i][2].startswith("- "):
        line, _, content = rows[i]
        m = _KEY.match(content)
        if not m:
            raise ValueError(f"line {line}: cannot read {content!r}")
        key = m.group(1).strip("'\"")
        val, i = _value(rows, i, indent, raw, m.group(2), line)
        out[S(key, line)] = val
    return out, i


def _seq(rows, i, indent, raw):
    out: list = []
    while i < len(rows) and rows[i][1] == indent and (rows[i][2] == "-" or rows[i][2].startswith("- ")):
        line, _, content = rows[i]
        rest = content[1:].lstrip()
        if not rest:
            val, i = _block(rows, i + 1, rows[i + 1][1], raw) if i + 1 < len(rows) and rows[i + 1][1] > indent else (None, i + 1)
        elif _KEY.match(rest) and not rest.startswith(("'", '"')) or (rest[:1] in "'\"" and _KEY.match(rest)):
            inner = indent + (len(content) - len(rest))
            rows[i] = [line, inner, rest]
            val, i = _map(rows, i, inner, raw)
        else:
            val, i = _scalar(_strip_comment(rest), line), i + 1
        out.append(val)
    return out, i
