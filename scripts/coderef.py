#!/usr/bin/env python3
"""Code refs: resolve a ref to real lines at a commit, so no agent types code or a URL by hand.

    understando snippet <path>[::symbol] [--match RE] [--part whole|signature|body] [--context N[,M]]
                        [--head SHA] [--json]

A code ref is one of:
  {"path", "symbol", "part"?, "match"?, "context"?}   an anchor (preferred): a symbol at the commit
  {"path", "match", "context"?}                       an anchor on a unique text in the file
  {"path", "start"?, "end"?}                          a line range (discouraged: it drifts)

  symbol    a dotted name: "run_document", "Editor.edit", "_idle", "DOCGEN_IMPORTS". Python
            resolves it with the stdlib ast (functions, classes, and module or class level
            assignments); TS and JS with a balanced-brace scan; other files with a regex (Lean: `theorem|def|lemma
            <name>`; TLA+: a `<Name> ==` definition; then the indented lines below it).
            A bare name that is not top level matches the last part of a dotted name.
  part      whole (default: with the decorators and the comment lines right above), signature
            (the header), body.
  match     text inside the symbol (or the file). "/RE/" is a regex, else a literal. It must
            occur exactly once. A regex with a group points at the group only.
  context   lines around the match: N, or [before, after]. Default 0.

A ref that resolves to 0 places, or to more than 1, raises AnchorError. Nothing writes resolved
line numbers back into the data: explain.py writes them to <run>/refs.resolved.json.

Control edits use the same anchors. The anchor ops:
  delete-line         delete the target lines. In Python, the whole statement that starts on the
                      target line (an if or elif with its block); an emptied block gets `pass`.
  invert-condition    Python only: negate the innermost condition, boolean operand or comparison
                      that holds the target (`a < b` -> `a >= b`, `not x` -> `x`, `x` -> `not x`).
  replace-with        replace the target with "with" (one line, at most 80 characters).
                      "span": "statement" replaces the whole Python statement on the target line.
  drop-allowlist-row  Python: remove the innermost list, tuple, set or dict item that holds the
                      target, with its comma. Other files: delete the target lines.
  corrupt-byte        flip one bit of the first target byte (or of "offset").
"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MAX_LINES = 30
MAX_WITH = 80
ANCHOR_OPS = ("delete-line", "invert-condition", "replace-with", "drop-allowlist-row")
JS_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"}
CACHE_NAME = "refs.resolved.json"


class AnchorError(ValueError):
    """A ref resolves to no place, or to more than one."""


# ---- git ------------------------------------------------------------------------------------

_SHOW: dict[tuple[str, str, str], str | None] = {}


def show(repo: str | Path, head: str, path: str) -> str | None:
    key = (str(repo), head, path)
    if key not in _SHOW:
        out = subprocess.run(["git", "-C", str(repo), "show", f"{head}:{path}"], capture_output=True)
        _SHOW[key] = out.stdout.decode("utf-8", "replace") if out.returncode == 0 else None
    return _SHOW[key]


def rev(repo: str | Path, name: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "-q", f"{name}^{{commit}}"], capture_output=True, text=True)
    if out.returncode != 0:
        raise AnchorError(f"no commit {name!r} in {repo}")
    return out.stdout.strip()


def remote_slug(repo: str | Path) -> str | None:
    """owner/name of the GitHub remote `origin`, or None."""
    out = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"], capture_output=True, text=True)
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", out.stdout.strip()) if out.returncode == 0 else None
    return f"{m.group(1)}/{m.group(2)}" if m else None


def permalink(repo: str | Path, head: str, path: str, start: int | None = None, end: int | None = None,
              slug: str | None = None) -> str | None:
    """The GitHub permalink blob/<sha>/<path>#Lx-Ly, from the git remote (else `slug`, owner/name)."""
    owner = remote_slug(repo) or slug
    if not owner or not re.fullmatch(r"[\w.-]+/[\w.-]+", owner):
        return None
    sha = rev(repo, head)
    frag = "" if not start else f"#L{start}" if not end or end == start else f"#L{start}-L{end}"
    return f"https://github.com/{owner}/blob/{sha}/{path}{frag}"


# ---- text positions ---------------------------------------------------------------------------

def line_starts(text: str) -> list[int]:
    starts, i = [0], 0
    while True:
        i = text.find("\n", i)
        if i < 0:
            return starts
        i += 1
        starts.append(i)


def line_of(starts: list[int], offset: int) -> int:
    """The 1-based line of a character offset."""
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def ast_offset(lines: list[str], starts: list[int], lineno: int, col: int) -> int:
    """A character offset from an ast (lineno, UTF-8 byte col)."""
    return starts[lineno - 1] + len(lines[lineno - 1].encode("utf-8")[:col].decode("utf-8", "replace"))


def node_span(lines: list[str], starts: list[int], node: ast.AST) -> tuple[int, int]:
    return (ast_offset(lines, starts, node.lineno, node.col_offset),
            ast_offset(lines, starts, node.end_lineno, node.end_col_offset))


# ---- symbols --------------------------------------------------------------------------------

@dataclass
class Sym:
    qual: str
    start: int          # whole, with decorators
    end: int
    sig_end: int
    body_start: int
    node: ast.AST | None = None


def _header_end(lines: list[str], first: int) -> int:
    """The line of the colon that ends a Python def or class header that starts on `first`."""
    depth, quote = 0, None
    for n in range(first, len(lines) + 1):
        line = lines[n - 1]
        i = 0
        while i < len(line):
            ch = line[i]
            if quote:
                if ch == "\\":
                    i += 1
                elif line.startswith(quote, i):
                    i += len(quote) - 1
                    quote = None
            elif ch == "#":
                break
            elif ch in "\"'":
                quote = line[i:i + 3] if line[i:i + 3] in ('"""', "'''") else ch
                i += len(quote) - 1
            elif ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == ":" and depth == 0:
                return n
            i += 1
    return first


def _lead(lines: list[str], first: int) -> int:
    """The first line of the comment lines right above `first` (no blank line between)."""
    while first > 1 and lines[first - 2].lstrip().startswith("#"):
        first -= 1
    return first


def python_symbols(text: str, path: str = "") -> list[Sym]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise AnchorError(f"{path}: Python does not parse: {exc}") from None
    lines = text.splitlines()
    out: list[Sym] = []

    def visit(body: list[ast.stmt], prefix: str, names: bool = True) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = prefix + node.name
                start = _lead(lines, min([d.lineno for d in node.decorator_list] + [node.lineno]))
                sig = _header_end(lines, node.lineno)
                out.append(Sym(qual, start, node.end_lineno, sig, node.body[0].lineno, node))
                visit(node.body, qual + ".", isinstance(node, ast.ClassDef))
            elif names and isinstance(node, (ast.Assign, ast.AnnAssign, ast.TypeAlias if hasattr(ast, "TypeAlias") else ast.Assign)):
                targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None) or node.name]
                for t in targets:
                    if isinstance(t, ast.Name):
                        out.append(Sym(prefix + t.id, _lead(lines, node.lineno), node.end_lineno, node.lineno, node.lineno, node))
            elif isinstance(node, (ast.If, ast.Try)) and not prefix and names:
                # Module-level `if TYPE_CHECKING:` and `try: import` blocks still define top-level names.
                visit(node.body, prefix)
                visit(getattr(node, "orelse", []), prefix)

    visit(tree.body, "")
    return out


_JS_DECL = r"^[ \t]*(?:export[ \t]+)?(?:default[ \t]+)?(?:declare[ \t]+)?(?:abstract[ \t]+)?(?:async[ \t]+)?" \
           r"(?:function\*?|class|interface|type|enum|const|let|var|namespace)[ \t]+{name}\b"
_JS_MEMBER = r"^[ \t]*(?:(?:public|private|protected|static|readonly|async|override|get|set)[ \t]+)*\*?{name}[ \t]*(?:[(<]|[?!]?[ \t]*[:=])"


def _js_block_end(text: str, starts: list[int], offset: int) -> tuple[int, int]:
    """(line of the opening brace, line of the matching close) for a JS or TS declaration at
    `offset`. A declaration with no block ends at its first `;` or blank line at depth 0."""
    depth, i, n, opened = 0, offset, len(text), None
    while i < n:
        ch = text[i]
        if text.startswith("//", i):
            i = text.find("\n", i)
            i = n if i < 0 else i
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if ch in "\"'`":
            j = i + 1
            while j < n and text[j] != ch:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if ch in "({[":
            if ch == "{" and depth == 0 and opened is None:
                opened = line_of(starts, i)
            depth += 1
        elif ch in ")}]":
            depth -= 1
            if depth == 0 and ch == "}" and opened is not None:
                return opened, line_of(starts, i)
        elif depth == 0 and (ch == ";" or text.startswith("\n\n", i)):
            line = line_of(starts, i)
            return line, line
        i += 1
    last = line_of(starts, n - 1)
    return opened or last, last


def js_symbols(text: str, symbol: str) -> list[Sym]:
    starts = line_starts(text)
    parts = symbol.split(".")
    regions = [(0, len(text))]
    found: list[Sym] = []
    for depth, name in enumerate(parts):
        pat = re.compile((_JS_DECL if depth == 0 else _JS_MEMBER).format(name=re.escape(name)), re.M)
        found = []
        for lo, hi in regions:
            for m in pat.finditer(text, lo, hi):
                first = line_of(starts, m.start())
                sig, end = _js_block_end(text, starts, m.start())
                found.append(Sym(".".join(parts[:depth + 1]), first, end, sig, min(sig + 1, end)))
        regions = [(starts[s.sig_end - 1], starts[s.end - 1] if s.end - 1 < len(starts) else len(text)) for s in found]
    return found


_GENERIC_DECL = r"^[ \t]*(?:(?:pub|export|private|public|protected|static|async|noncomputable|partial|@\w+)[ \t]+)*" \
                r"(?:def|fn|func|function|class|struct|enum|trait|impl|interface|module|sub|proc|theorem|lemma|" \
                r"structure|inductive|abbrev|instance|let|const|type|var|val|object)[ \t]+{name}\b|^{name}[ \t]*(?:\(|==|:=)"
# Lean: `theorem|def|lemma <name>`. TLA+: a `<Name> ==` definition, with or without parameters.
_LEAN_DECL = r"^(?:@\[[^\]]*\][ \t]*)?(?:(?:private|protected|noncomputable|partial|unsafe)[ \t]+)*(?:theorem|def|lemma)[ \t]+(?:[\w.']+\.)?{name}\b"
_TLA_DECL = r"^(?:LOCAL[ \t]+)?{name}(?:[ \t]*\([^)]*\))?[ \t]*=="


def generic_symbols(text: str, symbol: str, suffix: str = "") -> list[Sym]:
    """The regex fallback: a declaration line, then a brace block or the indented lines below."""
    lines = text.splitlines()
    starts = line_starts(text)
    name = symbol.split(".")[-1]
    out = []
    decl = {".lean": _LEAN_DECL, ".tla": _TLA_DECL}.get(suffix, _GENERIC_DECL)
    for m in re.finditer(decl.format(name=re.escape(name)), text, re.M):
        first = line_of(starts, m.start())
        line = lines[first - 1]
        if "{" in line:
            sig, end = _js_block_end(text, starts, m.start())
        else:
            indent = len(line) - len(line.lstrip())
            end = first
            for n in range(first + 1, len(lines) + 1):
                cur = lines[n - 1]
                if cur.strip() and len(cur) - len(cur.lstrip()) <= indent:
                    break
                if cur.strip():
                    end = n
            sig = first
        out.append(Sym(symbol, first, end, sig, min(sig + 1, end)))
    return out


def find_symbol(path: str, text: str, symbol: str) -> Sym:
    suffix = Path(path).suffix
    if suffix == ".py":
        syms = python_symbols(text, path)
        hits = [s for s in syms if s.qual == symbol] or [s for s in syms if s.qual.endswith("." + symbol)]
    elif suffix in JS_EXT:
        hits = js_symbols(text, symbol)
    else:
        hits = generic_symbols(text, symbol, suffix)
    if not hits:
        raise AnchorError(f"{path}::{symbol}: no such symbol")
    if len(hits) > 1:
        raise AnchorError(f"{path}::{symbol}: ambiguous, {len(hits)} places (lines {', '.join(str(h.start) for h in hits)})")
    return hits[0]


# ---- resolution -----------------------------------------------------------------------------

@dataclass
class Resolved:
    path: str
    start: int
    end: int
    text: str            # the whole file
    region: tuple[int, int]
    span: tuple[int, int] | None = None   # character offsets of the match target
    sym: Sym | None = None
    cut: bool = False

    @property
    def lines(self) -> list[str]:
        return self.text.splitlines()[self.start - 1:self.end]

    @property
    def excerpt(self) -> str:
        return "\n".join(self.lines)


def is_anchor(ref: dict) -> bool:
    return "symbol" in ref or "match" in ref


def pattern(match: str) -> re.Pattern:
    if len(match) > 2 and match.startswith("/") and match.endswith("/"):
        return re.compile(match[1:-1], re.M)
    return re.compile(re.escape(match))


def find_match(path: str, text: str, region: tuple[int, int], match: str, where: str) -> tuple[int, int]:
    starts = line_starts(text)
    lo = starts[region[0] - 1]
    hi = starts[region[1]] if region[1] < len(starts) else len(text)
    hits = list(pattern(match).finditer(text, lo, hi))
    if len(hits) != 1:
        lines = ", ".join(str(line_of(starts, h.start())) for h in hits[:8])
        raise AnchorError(f"{where}: match {match!r} occurs {len(hits)} times" + (f" (lines {lines})" if hits else "") + "; it must occur once")
    m = hits[0]
    return m.span(1) if m.re.groups and m.group(1) is not None else m.span()


def resolve_text(path: str, text: str, ref: dict, cap: bool = True) -> Resolved:
    """Resolve a ref against the text of `path`. Raises AnchorError."""
    n_lines = len(text.splitlines())
    where = path + (f"::{ref['symbol']}" if ref.get("symbol") else "")
    if is_anchor(ref):
        if "start" in ref or "end" in ref:
            raise AnchorError(f"{where}: an anchor has no start or end")
        sym = find_symbol(path, text, ref["symbol"]) if ref.get("symbol") else None
        part = ref.get("part", "whole")
        if sym is None:
            region = (1, n_lines)
        elif part == "whole":
            region = (sym.start, sym.end)
        elif part == "signature":
            region = (sym.node.lineno if isinstance(sym.node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else sym.start, sym.sig_end)
        elif part == "body":
            region = (sym.body_start, sym.end)
        else:
            raise AnchorError(f"{where}: unknown part {part!r}")
        start, end, span = region[0], region[1], None
        if ref.get("match"):
            span = find_match(path, text, region, ref["match"], where)
            starts = line_starts(text)
            first, last = line_of(starts, span[0]), line_of(starts, max(span[0], span[1] - 1))
            ctx = ref.get("context", 0)
            before, after = (ctx, ctx) if isinstance(ctx, int) else (ctx[0], ctx[1])
            start, end = max(region[0], first - before), min(region[1], last + after)
        res = Resolved(path, start, end, text, region, span, sym)
    else:
        start = ref.get("start", 1)
        end = ref.get("end", start + MAX_LINES - 1)
        if start > n_lines:
            raise AnchorError(f"{path}: line {start} is past the end ({n_lines} lines)")
        res = Resolved(path, start, min(end, n_lines), text, (1, n_lines))
    if cap and res.end - res.start + 1 > MAX_LINES:
        res.end, res.cut = res.start + MAX_LINES - 1, True
    return res


def resolve(repo: str | Path, head: str, ref: dict, cap: bool = True) -> Resolved:
    text = show(repo, head, ref["path"])
    if text is None:
        raise AnchorError(f"{ref['path']}: no such file at {head[:10]}")
    return resolve_text(ref["path"], text, ref, cap)


def ref_key(ref: dict) -> str:
    return json.dumps({k: v for k, v in ref.items() if k != "note"}, sort_keys=True)


def write_cache(run: str | Path, head: str, resolved: dict[str, Resolved]) -> Path:
    """The resolved line numbers, for people and doctor. The data keeps only the anchors."""
    dest = Path(run) / CACHE_NAME
    body = {"head": head, "refs": [{"ref": json.loads(k), "start": r.start, "end": r.end} for k, r in sorted(resolved.items())]}
    dest.write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8")
    return dest


def walk_refs(data: dict, extra: dict | None = None):
    """(where, ref) for each code ref in a trust map and an explain.json."""
    for c in data.get("claims", []):
        for i, ref in enumerate(c.get("code", [])):
            yield f"claim {c['id']} code[{i}]", ref
    for i, step in enumerate(((extra or {}).get("loop") or {}).get("steps") or [], 1):
        for j, ref in enumerate(step.get("code", [])):
            yield f"explain loop step {i} code[{j}]", ref


def walk_edits(data: dict):
    for k in data.get("controls", []):
        for i, e in enumerate(k.get("edits", [])):
            yield k, f"control {k['id']} edit[{i}]", e


# ---- control edits --------------------------------------------------------------------------

def _stmt_on_line(tree: ast.AST, line: int) -> tuple[ast.stmt, ast.AST, str] | None:
    """The outermost statement that starts on `line`, with its parent and the parent field."""
    best = None
    for parent in ast.walk(tree):
        for field in ("body", "orelse", "finalbody", "handlers"):
            items = getattr(parent, field, None)
            for node in items if isinstance(items, list) else []:
                if isinstance(node, ast.stmt) and node.lineno == line:
                    if best is None or (node.end_lineno - node.lineno) > (best[0].end_lineno - best[0].lineno):
                        best = (node, parent, field)
    return best


def _delete_statement(path: str, text: str, res: Resolved) -> str:
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    line = line_of(line_starts(text), res.span[0]) if res.span else res.start
    hit = _stmt_on_line(tree, line)
    if not hit:
        return "".join(lines[:res.start - 1] + lines[res.end:])
    node, parent, field = hit
    is_elif = isinstance(node, ast.If) and lines[node.lineno - 1].lstrip().startswith("elif")
    tail = getattr(node, "orelse", None) or getattr(node, "finalbody", None) or getattr(node, "handlers", None)
    if tail and not is_elif:
        raise AnchorError(f"{path}:{node.lineno}: deleting this statement leaves its else, except or finally block without a head")
    last = node.body[-1].end_lineno if (tail and is_elif) else node.end_lineno
    indent = lines[node.lineno - 1][:len(lines[node.lineno - 1]) - len(lines[node.lineno - 1].lstrip())]
    siblings = getattr(parent, field)
    keep = [] if (len(siblings) > 1 or is_elif) else [indent + "pass\n"]
    return "".join(lines[:node.lineno - 1] + keep + lines[last:])


_FLIP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE, ast.LtE: ast.Gt,
         ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}


def _invert(path: str, text: str, res: Resolved) -> str:
    tree = ast.parse(text)
    lines = text.splitlines()
    starts = line_starts(text)
    cands: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While, ast.IfExp, ast.Assert)):
            cands.append(node.test)
        elif isinstance(node, ast.Return) and node.value is not None:
            cands.append(node.value)
        elif isinstance(node, ast.BoolOp):
            cands.extend(node.values)
        elif isinstance(node, ast.Compare):
            cands.append(node)
        elif isinstance(node, ast.comprehension):
            cands.extend(node.ifs)
    span = res.span or (starts[res.start - 1], starts[res.start - 1] + len(lines[res.start - 1]))
    holding = [(node_span(lines, starts, c), c) for c in cands]
    holding = [(s, c) for s, c in holding if s[0] <= span[0] and span[1] <= s[1]]
    if not holding:
        raise AnchorError(f"{path}:{line_of(starts, span[0])}: no condition holds the anchor")
    (lo, hi), node = min(holding, key=lambda x: x[0][1] - x[0][0])
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _FLIP:
        new = ast.Compare(node.left, [_FLIP[type(node.ops[0])]()], node.comparators)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        new = node.operand
    else:
        new = ast.UnaryOp(ast.Not(), node)
    out = ast.unparse(new)
    if isinstance(new, ast.UnaryOp) and isinstance(node, (ast.BoolOp, ast.IfExp, ast.Lambda, ast.NamedExpr)):
        out = f"not ({ast.unparse(node)})"
    return text[:lo] + out + text[hi:]


def _drop_item(path: str, text: str, res: Resolved) -> str:
    if not path.endswith(".py"):
        lines = text.splitlines(keepends=True)
        return "".join(lines[:res.start - 1] + lines[res.end:])
    tree = ast.parse(text)
    lines = text.splitlines()
    starts = line_starts(text)
    span = res.span or (starts[res.start - 1], starts[res.start - 1] + len(lines[res.start - 1]))
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            items = [node_span(lines, starts, e) for e in node.elts]
        elif isinstance(node, ast.Dict) and None not in node.keys:
            items = [(node_span(lines, starts, k)[0], node_span(lines, starts, v)[1]) for k, v in zip(node.keys, node.values)]
        else:
            continue
        for i, (lo, hi) in enumerate(items):
            if lo <= span[0] and span[1] <= hi and (best is None or hi - lo < best[1] - best[0]):
                best = (lo, hi, items, i)
    if not best:
        raise AnchorError(f"{path}:{line_of(starts, span[0])}: no list, tuple, set or dict item holds the anchor")
    lo, hi, items, i = best
    if i + 1 < len(items):
        return text[:lo] + text[items[i + 1][0]:]
    if i > 0:
        return text[:items[i - 1][1]] + text[hi:]
    return text[:lo] + text[hi:].lstrip(",")


def anchor_ref(edit: dict) -> dict:
    return {k: edit[k] for k in ("path", "symbol", "part", "match", "context") if k in edit}


def cli_edit(path: str, op: str | None, symbol: str | None, match: str | None, with_: str | None) -> dict:
    """The anchor edit that a script's --op, --symbol, --match and --with flags name."""
    edit = {"op": op or ("replace-with" if with_ is not None else "delete-line"), "path": path}
    for key, val in (("symbol", symbol), ("match", match), ("with", with_)):
        if val is not None:
            edit[key] = val
    return edit


def apply_text(text: str, edit: dict) -> str:
    """The file text after one anchor op. Raises AnchorError when the anchor does not resolve once."""
    path, op = edit["path"], edit["op"]
    if not is_anchor(edit):
        raise AnchorError(f"{path}: {op} needs a symbol or a match")
    res = resolve_text(path, text, anchor_ref(edit), cap=False)
    py = path.endswith(".py")
    if op == "delete-line":
        if py:
            return _delete_statement(path, text, res)
        lines = text.splitlines(keepends=True)
        return "".join(lines[:res.start - 1] + lines[res.end:])
    if op == "invert-condition":
        if not py:
            raise AnchorError(f"{path}: invert-condition is for Python only")
        return _invert(path, text, res)
    if op == "replace-with":
        new = edit.get("with")
        if new is None or "\n" in new or len(new) > MAX_WITH:
            raise AnchorError(f"{path}: replace-with needs a \"with\" of one line, at most {MAX_WITH} characters")
        if edit.get("span") == "statement":
            if not py or not res.span:
                raise AnchorError(f"{path}: span statement needs a Python file and a match")
            lines = text.splitlines(keepends=True)
            hit = _stmt_on_line(ast.parse(text), line_of(line_starts(text), res.span[0]))
            if not hit:
                raise AnchorError(f"{path}: no statement starts on the anchor line")
            node = hit[0]
            first = lines[node.lineno - 1]
            indent = first[:len(first) - len(first.lstrip())]
            return "".join(lines[:node.lineno - 1] + [indent + new + "\n"] + lines[node.end_lineno:])
        if not res.span:
            raise AnchorError(f"{path}: replace-with needs a match")
        return text[:res.span[0]] + new + text[res.span[1]:]
    if op == "drop-allowlist-row":
        return _drop_item(path, text, res)
    raise AnchorError(f"{path}: unknown anchor op {op!r}")


def corrupt_offset(text_bytes: bytes, edit: dict) -> int:
    if not is_anchor(edit):
        return edit.get("offset", len(text_bytes) // 2)
    text = text_bytes.decode("utf-8")
    res = resolve_text(edit["path"], text, anchor_ref(edit), cap=False)
    at = res.span[0] if res.span else line_starts(text)[res.start - 1]
    return len(text[:at].encode("utf-8"))


def unified(path: str, before: str, after: str, context: int = 2) -> str:
    """A unified patch of one file, with the real line numbers."""
    return "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                        f"a/{path}", f"b/{path}", n=context))


def edit_text(text: str, edit: dict) -> str:
    """The file text after one text edit: an anchor op, or a legacy replace or append."""
    op = edit["op"]
    if op in ANCHOR_OPS:
        return apply_text(text, edit)
    if op == "replace":
        found = text.count(edit["find"])
        if found != edit.get("count", 1):
            raise AnchorError(f"{edit['path']}: find text occurs {found} times, expected {edit.get('count', 1)}")
        return text.replace(edit["find"], edit["replace"])
    if op == "append":
        return text + edit["text"]
    if op == "delete-file":
        return ""
    raise AnchorError(f"{edit['path']}: no text form for {op}")


def control_patches(repo: str | Path, head: str, edits: list[dict]) -> list[tuple[str, str | None]]:
    """(path, patch) for each file that a control changes, from the same resolution that
    run_control applies. A byte edit has no text patch (None)."""
    texts: dict[str, tuple[str, str | None]] = {}
    for edit in edits:
        path = edit["path"]
        if path not in texts:
            text = show(repo, head, path)
            if text is None:
                raise AnchorError(f"{path}: no such file at {head[:10]}")
            texts[path] = (text, text)
        before, after = texts[path]
        texts[path] = (before, None if edit["op"] == "corrupt-byte" or after is None else edit_text(after, edit))
    return [(p, None if after is None else unified(p, before, after)) for p, (before, after) in texts.items()]


def split_patch(diff: str) -> list[tuple[str, str]]:
    """git diff output, one (path, patch) per file."""
    out = []
    for chunk in re.split(r"(?m)^(?=diff --git )", diff):
        m = re.match(r"diff --git a/(\S+) b/", chunk)
        if m:
            out.append((m.group(1), chunk))
    return out


# ---- the no-hand-copy guard -------------------------------------------------------------------

MIN_CHARS = 12


def _norm(line: str) -> str:
    return " ".join(line.split())


def _windows(value: str) -> list[tuple[str, str]]:
    lines = [_norm(x) for x in value.splitlines()]
    lines = [x for x in lines if x]
    return [(a, b) for a, b in zip(lines, lines[1:]) if len(re.sub(r"\W", "", a + b)) >= MIN_CHARS]


def strings(value, where: str = "$"):
    if isinstance(value, str):
        yield where, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from strings(v, f"{where}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from strings(v, f"{where}[{i}]")


def pasted(repo: str | Path, head: str, inputs: list[tuple[str, str]]) -> list[str]:
    """Each input string of 2 or more lines whose 2 consecutive lines (whitespace-normalised)
    occur as 2 consecutive lines of a tracked file at `head`. inputs: (where, text)."""
    found = []
    for where, value in inputs:
        for a, b in _windows(value):
            out = subprocess.run(["git", "-C", str(repo), "grep", "-I", "-F", "-n", "--full-name", "-e", a, head],
                                 capture_output=True, text=True)
            hit = None
            for row in out.stdout.splitlines():
                _, path, n, _ = row.split(":", 3)
                lines = [_norm(x) for x in (show(repo, head, path) or "").splitlines()]
                i = int(n) - 1
                if lines[i] != a:
                    continue
                j = i + 1
                while j < len(lines) and not lines[j]:
                    j += 1
                if j < len(lines) and lines[j] == b:
                    hit = f"{path}:{n}"
                    break
            if hit:
                found.append(f"{where}: pasted code from {hit}: {a[:60]!r} ... Write a code ref instead (understando snippet).")
                break
    return found


def guard_inputs(data: dict, extra: dict | None, mdx: list[Path]) -> list[tuple[str, str]]:
    """The text that a person or a model writes: explain.json, the plain and text fields of the
    trust map (the PR-body input too), and each MDX file that explain.py reads."""
    out = list(strings(extra or {}, "explain.json"))
    for section in ("claims", "verifiers", "controls", "promises", "invariants"):
        for item in data.get(section, []):
            for key in ("text", "plain", "reason", "description"):
                if key in item:
                    out += list(strings(item[key], f"trust-map {item.get('id', section)}.{key}"))
            if item.get("waiver"):
                out += list(strings(item["waiver"].get("reason", ""), f"trust-map {item['id']}.waiver"))
    out += list(strings(data.get("narrative") or "", "trust-map narrative"))
    out += list(strings(data.get("notes") or [], "trust-map notes"))
    for p in mdx:
        out.append((str(p), p.read_text(encoding="utf-8")))
    return out


# ---- the snippet verb -----------------------------------------------------------------------

def suggest(path: str, text: str, start: int, end: int) -> list[dict] | None:
    """The anchors that resolve to exactly start..end: one symbol part, else consecutive whole
    symbols, else a unique text in the innermost symbol with context."""
    syms: list[Sym] = python_symbols(text, path) if path.endswith(".py") else []
    holders = sorted([s for s in syms if s.start <= start and end <= s.end], key=lambda s: s.end - s.start)
    for s in holders:
        for part in ("whole", "body", "signature"):
            ref = {"path": path, "symbol": s.qual, **({"part": part} if part != "whole" else {})}
            try:
                r = resolve_text(path, text, ref, cap=False)
            except AnchorError:
                break
            if (r.start, r.end) == (start, end):
                return [ref]
    lines = text.splitlines()
    inside = sorted([s for s in syms if start <= s.start and s.end <= end], key=lambda s: s.start)
    top = [s for s in inside if not any(o is not s and o.start <= s.start and s.end <= o.end for o in inside)]
    if top and top[0].start == start and top[-1].end == end and all(
            not "".join(lines[a.end:b.start - 1]).strip() for a, b in zip(top, top[1:])):
        refs = [{"path": path, "symbol": s.qual} for s in top]
        try:
            if all(resolve_text(path, text, r, cap=False).start == s.start for r, s in zip(refs, top)):
                return refs
        except AnchorError:
            pass
    for s in holders[:1] + [None]:
        base = {"path": path, **({"symbol": s.qual} if s else {})}
        for line in range(start, end + 1):
            raw = lines[line - 1].strip()
            if len(re.sub(r"\W", "", raw)) < 4:
                continue
            for cut in sorted({len(raw), 60, 40, 24}):
                lit = raw[:cut].rstrip()
                if not lit or cut > len(raw):
                    continue
                ref = {**base, "match": lit}
                if line != start or line != end:
                    ref["context"] = [line - start, end - line] if line - start != end - line else line - start
                try:
                    r = resolve_text(path, text, ref, cap=False)
                except AnchorError:
                    continue
                if (r.start, r.end) == (start, end):
                    return [ref]
    return None


def main(c, argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="understando snippet", description="Print a resolved code excerpt with its line numbers "
                                 "and its GitHub permalink. Preview a ref with it; do not read or paste whole files.")
    ap.add_argument("target", help="path or path::symbol")
    ap.add_argument("--match", help='a literal, or "/RE/"; it must occur once')
    ap.add_argument("--part", choices=["whole", "signature", "body"])
    ap.add_argument("--context", help="N, or BEFORE,AFTER")
    ap.add_argument("--lines", help="START-END: a line range (discouraged)")
    ap.add_argument("--head", help="commit (default: the trust map head, else HEAD)")
    ap.add_argument("--suggest", action="store_true", help="with --lines: print the anchor that resolves to the same lines")
    args = ap.parse_args(argv)
    repo = c.repo or Path.cwd()
    data = c.data() if c.run else None
    head = rev(repo, args.head or (data or {}).get("head") or "HEAD")
    path, _, symbol = args.target.partition("::")
    ref: dict = {"path": path}
    if symbol:
        ref["symbol"] = symbol
    if args.match:
        ref["match"] = args.match
    if args.part:
        ref["part"] = args.part
    if args.context:
        nums = [int(x) for x in args.context.split(",")]
        ref["context"] = nums[0] if len(nums) == 1 else nums[:2]
    if args.lines:
        a, _, b = args.lines.partition("-")
        ref.update(start=int(a), end=int(b or a))
    try:
        if args.suggest:
            text = show(repo, head, path)
            if text is None or not args.lines:
                raise AnchorError("--suggest needs --lines and a file at the head")
            got = suggest(path, text, ref["start"], ref["end"])
            if not got:
                raise AnchorError(f"{path}:{ref['start']}-{ref['end']}: no anchor resolves to these lines; keep the range")
            print("\n".join(json.dumps(g, ensure_ascii=False) for g in got))
            return 0
        r = resolve(repo, head, ref)
    except AnchorError as exc:
        print(f"understando snippet: {exc}", file=sys.stderr)
        return 1
    link = permalink(repo, head, path, r.start, r.end, (data or {}).get("repo"))
    if c.json:
        print(json.dumps({"ref": ref, "head": head, "start": r.start, "end": r.end, "cut": r.cut, "permalink": link, "code": r.excerpt}))
        return 0
    print(f"{path}:{r.start}-{r.end} at {head[:10]}" + (" (cut at 30 lines)" if r.cut else ""))
    if link:
        print(link)
    width = len(str(r.end))
    for n, line in enumerate(r.lines, r.start):
        print(f"{n:>{width}}  {line}")
    return 0


def apply_file(path: str, edit: dict) -> None:
    """Apply one anchor edit to a file in place (the learn app calls this). Raises AnchorError."""
    p = Path(path)
    if edit["op"] == "corrupt-byte":
        data = bytearray(p.read_bytes())
        data[corrupt_offset(bytes(data), edit)] ^= 0x01
        p.write_bytes(bytes(data))
        return
    p.write_text(apply_text(p.read_text(encoding="utf-8"), edit), encoding="utf-8")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--apply-edit"]:
        # python3 -I coderef.py --apply-edit FILE EDIT_JSON: one anchor edit, in place.
        try:
            apply_file(sys.argv[2], json.loads(sys.argv[3]))
        except (AnchorError, KeyError, ValueError) as exc:
            print(f"ANCHOR ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ctx as context  # noqa: E402
    opts_repo = None
    rest = sys.argv[1:]
    if "--repo" in rest:
        i = rest.index("--repo")
        opts_repo = rest[i + 1]
        rest = rest[:i] + rest[i + 2:]
    sys.exit(main(context.resolve(None, opts_repo, None, "--json" in rest), [a for a in rest if a != "--json"]))
