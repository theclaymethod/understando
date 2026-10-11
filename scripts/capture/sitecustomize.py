"""Record the calls of named functions in a Python process, for scripts/example.py.

scripts/example.py puts this folder first on PYTHONPATH and sets two variables:

  UNDERSTANDO_CAPTURE_SPEC  JSON: [{"name": "run", "target": "pkg.mod:func" | "pkg.mod:Class.method",
                            "args": false}, ...]
  UNDERSTANDO_CAPTURE_OUT   the JSON file to write when the process ends

When a target module finishes its import, its function (or method) is wrapped: each call appends
{"args": [...] (when "args" is true), "result": ...} (or "raised": "Type: message") to the record of its name. A later
`from pkg.mod import func` gets the wrapper too. A value is serialized by its own `trace()`, then
`to_dict()`, then as a dataclass, a mapping or a sequence; any other value is its repr. The
process runs as before: a wrapper only records. Standard library only.
"""

from __future__ import annotations

import atexit
import dataclasses
import functools
import importlib.abc
import importlib.machinery
import inspect
import json
import os
import sys

_SPEC = json.loads(os.environ.get("UNDERSTANDO_CAPTURE_SPEC") or "[]")
_OUT = os.environ.get("UNDERSTANDO_CAPTURE_OUT")
_RECORDS: dict[str, list] = {r["name"]: [] for r in _SPEC}
_PATCHED: set[str] = set()


def value(x, depth: int = 0):
    """A JSON value for x: its own serializer first, then its structure, else its repr."""
    if depth > 40:
        return repr(x)
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    for method in ("trace", "to_dict"):
        fn = getattr(x, method, None)
        if callable(fn) and not isinstance(x, type):
            try:
                return value(fn(), depth + 1)
            except TypeError:
                pass
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return {f.name: value(getattr(x, f.name), depth + 1) for f in dataclasses.fields(x)}
    if isinstance(x, dict):
        return {str(k): value(v, depth + 1) for k, v in x.items()}
    if isinstance(x, (list, tuple, set, frozenset)):
        items = sorted(x, key=repr) if isinstance(x, (set, frozenset)) else x
        return [value(v, depth + 1) for v in items]
    return repr(x)


def _wrap(fn, rec: dict):
    store = _RECORDS[rec["name"]]

    def note(args, kwargs, result, raised=None):
        row = {"raised": f"{type(raised).__name__}: {raised}"} if raised is not None else {"result": value(result)}
        if rec.get("args"):
            row["args"] = [value(a) for a in args]
            if kwargs:
                row["kwargs"] = {k: value(v) for k, v in kwargs.items()}
        store.append(row)

    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def awrapper(*args, **kwargs):
            try:
                result = await fn(*args, **kwargs)
            except Exception as exc:
                note(args, kwargs, None, exc)
                raise
            note(args, kwargs, result)
            return result
        return awrapper

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            note(args, kwargs, None, exc)
            raise
        note(args, kwargs, result)
        return result
    return wrapper


def _patch(module) -> None:
    for rec in _SPEC:
        mod, _, attr = rec["target"].partition(":")
        if mod != module.__name__ or rec["target"] in _PATCHED:
            continue
        owner, parts = module, attr.split(".")
        for part in parts[:-1]:
            owner = getattr(owner, part)
        original = inspect.getattr_static(owner, parts[-1])
        if isinstance(original, (staticmethod, classmethod)):
            setattr(owner, parts[-1], type(original)(_wrap(original.__func__, rec)))
        else:
            setattr(owner, parts[-1], _wrap(original, rec))
        _PATCHED.add(rec["target"])


class _Loader(importlib.abc.Loader):
    def __init__(self, inner):
        self.inner = inner

    def create_module(self, spec):
        return self.inner.create_module(spec)

    def exec_module(self, module):
        self.inner.exec_module(module)
        _patch(module)


class _Finder(importlib.abc.MetaPathFinder):
    targets = {r["target"].partition(":")[0] for r in _SPEC}

    def find_spec(self, name, path, target=None):
        if name not in self.targets:
            return None
        for finder in sys.meta_path:
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(name, path, target)
            if spec is not None:
                if spec.loader is not None and hasattr(spec.loader, "exec_module"):
                    spec.loader = _Loader(spec.loader)
                return spec
        return None


def _write() -> None:
    if _OUT:
        missing = [r["target"] for r in _SPEC if r["target"] not in _PATCHED]
        with open(_OUT, "w", encoding="utf-8") as f:
            json.dump({"records": _RECORDS, "unpatched": missing}, f, ensure_ascii=False, indent=1, default=repr)


class _FrontList(list):
    """sys.meta_path that keeps the capture finder first: a later import hook (pytest's
    assertion rewriter) goes in after it, so the capture still wraps the loader that hook gives."""

    def insert(self, index, item):
        super().insert(max(index, 1) if self and isinstance(self[0], _Finder) else index, item)


if _SPEC:
    sys.meta_path = _FrontList([_Finder(), *sys.meta_path])
    for loaded in list(sys.modules.values()):
        if getattr(loaded, "__name__", None) in _Finder.targets:
            _patch(loaded)
    atexit.register(_write)
