#!/usr/bin/env python3
"""Extract the worked examples of an explainer from synthetic sources: real values, with provenance.

    python3 scripts/example.py --spec examples.spec.json --map trust-map.json --repo <git repo> \
        --out examples.json [--refs refs.resolved.json] [--keep-sources]

The explain step leads each how-it-works level with one example of real data moving through the
flow (commands/explain.md). The agent writes the spec: which source to read, which station each
step shows, which values it shows, and the reason in plain words. This script reads every value
from the source; the spec holds no value. A step that names no value fails.

Sources (`sources` of an example, each with a name):

  run       a command at a commit (a test that drives a scripted session), in a scratch worktree of
            a private clone. `record` names the functions to record: capture/sitecustomize.py
            wraps each one and writes each call's result (and its arguments, with "args": true).
            The document is {name: [{"result", "args"?, "raised"?}, ...], "exit": n, "output": tail}.
  tlc       TLC on a TLA+ spec at a commit (formal_tlc.py check, one worker, so the trace is the
            same on each run): {status, violation, trace}.
  vector    one row of a replay or conformance vector file at a commit (a JSON file with a list of
            rows at `rows`, default "/vectors", or a JSONL file): the first row that matches each
            pointer of `match`, else row `index`. The document is {"index", "row"}.
  controls  planted-bug controls of the map: {id: {"control", "result", "check", "patch"}}.
  claim     one claim of the map and its derived values (--refs): {"claim", "derived", "checks"}.

A commit is "head" (the map head), "base", "ready" (the ready branch) or a SHA. The data sources
are synthetic only: the reviewed repo's fixtures, scripted tests, goldens, traces, vectors and
controls. A path under a private folder or an env file is refused.

A value is a JSON pointer that starts with the source name ("/session/run/0/result/outcome"), or
{"from": pointer, ...ops}: `where` {pointer: value} keeps the list items that match, `each` maps
each item through a pointer, `distinct` drops repeats in a row, `slice` [a, b] and `at` (-1 is the
last) pick items, `fields` keeps those keys of each object (a list, or {label: key} to name each
key for the reader; a key that starts with "/" is a pointer into the object), then one of `count`, `sha256`, `lines` [a, b].

Each example step in the output holds `in`, `decision` and `out` (each a list of {label, value,
from}), the `reason`, an optional `diff` ({path, before, after} or {path, patch}) and `code` ref, and `provenance`:
each source pointer that it read. Each source records its kind, the full commit, what it ran and
the sha256 of its document, so a reviewer can run it again. `assert` [{"value", "equals"}] in a
step fails the extraction when a real value differs from the one that the reason assumes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import tm  # noqa: E402

S = Path(__file__).resolve().parent
CAPTURE = S / "capture"
SCHEMA = 1
KINDS = ("run", "tlc", "vector", "controls", "claim")
# Never a source: member data, private harness folders, env files.
FORBIDDEN = re.compile(r"(^|/)(harness-h1/private[^/]*|\.env[^/]*)(/|$)", re.I)
TAIL = 60


def fail(message: str) -> None:
    tm.fail("example.py: " + message, 1)


def git(repo: str | Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if out.returncode != 0:
        fail(f"git {' '.join(args[:3])} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def guard_path(path: str) -> str:
    if not path or FORBIDDEN.search(path) or path.startswith("/") or ".." in Path(path).parts:
        fail(f"{path!r} is not a synthetic source path. Use a fixture, a scripted test, a golden, a trace or a vector of the repo.")
    return path


def commit_of(repo: str, data: dict, name: str) -> str:
    if name == "head":
        return data["head"]
    if name == "base":
        return data["base"]
    if name == "ready":
        ref = (data.get("ready") or {}).get("head") or f"refs/heads/understando/{data.get('pr')}-ready"
        return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    return git(repo, "rev-parse", "--verify", f"{name}^{{commit}}")


def sha(doc) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(doc, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def tail(text: str) -> str:
    return tm.redact("\n".join(text.rstrip().splitlines()[-TAIL:]).replace(str(Path.home()), "~"))


# ---- The sources ------------------------------------------------------------------------------

class Scratch:
    """A private clone of the repo (git clone --shared) and one worktree per commit, in a temp dir.
    The reviewed repo gets no worktree, no branch and no file."""

    def __init__(self, repo: str, data: dict):
        self.repo, self.data, self.trees = repo, data, {}
        self.dir = Path(tempfile.mkdtemp(prefix="understando-example-"))
        self.clone = self.dir / "clone"
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", repo, str(self.clone)], check=True, capture_output=True)

    def tree(self, commit: str, setup: bool) -> Path:
        if commit not in self.trees:
            root = self.dir / f"wt-{commit[:12]}"
            git(self.clone, "worktree", "add", "-q", "--detach", str(root), commit)
            self.trees[commit] = [root, False]
        root, ready = self.trees[commit]
        if setup and not ready:
            for step in self.data.get("setup", []):
                out = subprocess.run(step["argv"], cwd=root / step.get("cwd", "."), capture_output=True, text=True,
                                     timeout=step.get("timeout_s", 900), stdin=subprocess.DEVNULL)
                if out.returncode != 0:
                    fail(f"setup {' '.join(step['argv'])} failed at {commit[:10]}:\n{tail(out.stdout + out.stderr)}")
            self.trees[commit][1] = True
        return root

    def close(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


def source_run(src: dict, commit: str, scratch: Scratch) -> tuple[dict, dict]:
    record = src.get("record") or []
    if not record or not src.get("argv"):
        fail("a run source needs argv and record (the functions to record)")
    cwd = guard_path(src.get("cwd", ".")) if src.get("cwd", ".") != "." else "."
    root = scratch.tree(commit, bool(src.get("setup", True)))
    out_file = scratch.dir / f"capture-{os.getpid()}-{len(list(scratch.dir.glob('capture-*')))}.json"
    env = {**os.environ, "UNDERSTANDO_CAPTURE_SPEC": json.dumps(record), "UNDERSTANDO_CAPTURE_OUT": str(out_file),
           "PYTHONPATH": os.pathsep.join([str(CAPTURE), *filter(None, [os.environ.get("PYTHONPATH")])]),
           "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(src["argv"], cwd=root / cwd, env=env, capture_output=True, text=True,
                          timeout=src.get("timeout_s", 900), stdin=subprocess.DEVNULL)
    output = (proc.stdout + proc.stderr).replace(str(root), "<worktree>")
    if not out_file.is_file():
        fail(f"the run wrote no capture (exit {proc.returncode}): {' '.join(src['argv'])}\n{tail(output)}")
    capture = json.loads(out_file.read_text(encoding="utf-8"))
    if capture["unpatched"]:
        fail(f"the run never imported {', '.join(capture['unpatched'])}: check each record target")
    want = src.get("exit", 0)
    if want is not None and proc.returncode != want:
        fail(f"the run exits {proc.returncode}, the spec expects {want}: {' '.join(src['argv'])}\n{tail(output)}")
    doc = {**capture["records"], "exit": proc.returncode, "output": tail(output)}
    return doc, {"cwd": cwd, "argv": src["argv"], "record": record, "setup": [s["argv"] for s in scratch.data.get("setup", [])] if src.get("setup", True) else []}


def source_tlc(src: dict, commit: str, scratch: Scratch) -> tuple[dict, dict]:
    spec, cfg = guard_path(src["spec"]), guard_path(src.get("cfg") or src["spec"][:-4] + ".cfg")
    folder = scratch.dir / f"tla-{commit[:12]}"
    if not folder.exists():
        folder.mkdir()
        archive = subprocess.run(["git", "-C", scratch.repo, "archive", commit, str(Path(spec).parent)], capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", str(folder)], input=archive.stdout, check=True)
    argv = [sys.executable, str(S / "formal_tlc.py"), "check", "--spec", str(folder / spec), "--cfg", str(folder / cfg)]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=src.get("timeout_s", 900),
                          env={**os.environ, "UNDERSTANDO_TLC_WORKERS": "1"})
    if proc.returncode not in (0, 1):
        fail(f"TLC did not finish on {spec} at {commit[:10]} (exit {proc.returncode}):\n{tail(proc.stdout + proc.stderr)}")
    doc = json.loads(proc.stdout)
    want = src.get("status")
    if want and doc.get("status") != want:
        fail(f"TLC gives {doc.get('status')} on {cfg} at {commit[:10]}; the spec expects {want}")
    # One TLC worker: the same counterexample on each run, so the values can be checked again.
    return doc, {"spec": spec, "cfg": cfg, "argv": ["UNDERSTANDO_TLC_WORKERS=1", "python3", "scripts/formal_tlc.py", "check", "--spec", spec, "--cfg", cfg]}


def source_vector(src: dict, commit: str, scratch: Scratch) -> tuple[dict, dict]:
    path = guard_path(src["path"])
    text = git(scratch.repo, "show", f"{commit}:{path}")
    if path.endswith(".jsonl"):
        rows, header = [json.loads(line) for line in text.splitlines() if line.strip()], {}
    else:
        whole = json.loads(text)
        rows = pointer(whole, src.get("rows", "/vectors"))
        header = {k: v for k, v in whole.items() if not isinstance(v, list)} if isinstance(whole, dict) else {}
    match = src.get("match")
    if match:
        hits = [i for i, row in enumerate(rows) if all(pointer(row, p, None) == v for p, v in match.items())]
        if not hits:
            fail(f"no row of {path} at {commit[:10]} matches {json.dumps(match)}")
        index = hits[0]
    else:
        index = int(src.get("index", 0))
    return {"index": index, "row": rows[index], "header": header}, {"path": path, "match": match, "index": index, "rows": len(rows)}


def source_controls(src: dict, data: dict, repo: str) -> tuple[dict, dict]:
    import explain
    controls = {k["id"]: k for k in data["controls"]}
    verifiers = {v["id"]: v for v in data["verifiers"]}
    patches = explain.control_edits(repo, data)
    doc = {}
    for cid in src["ids"]:
        if cid not in controls:
            fail(f"no control {cid} in the map")
        k = controls[cid]
        v = verifiers[k["verifier"]]
        doc[cid] = {"control": {x: y for x, y in k.items() if x != "result"}, "result": k.get("result") or {},
                    "check": {"id": v["id"], "name": v.get("name"), "kind": v["kind"], "command": v.get("command"), "baseline": v.get("baseline")},
                    "patch": patches.get(cid, [])}
    return doc, {"ids": src["ids"], "from": "the controls of the map and their recorded results (understando controls)"}


def source_claim(src: dict, data: dict, refs: dict | None) -> tuple[dict, dict]:
    if not refs:
        fail("a claim source needs --refs (refs.resolved.json of `understando explain --no-html`)")
    claims = {c["id"]: c for c in data["claims"]}
    cid = src["id"]
    if cid not in claims:
        fail(f"no claim {cid} in the map")
    controls = {}
    for k in data["controls"]:
        controls.setdefault(k["verifier"], []).append({"id": k["id"], "description": k.get("description"), "result": k.get("result") or {}})
    verifiers = {v["id"]: v for v in data["verifiers"]}
    checks = {vid: {"name": verifiers[vid].get("name"), "kind": verifiers[vid]["kind"], "controls": controls.get(vid, [])}
              for vid in claims[cid].get("checks", []) if vid in verifiers}
    return {"claim": claims[cid], "derived": refs["derived"]["claims"][cid], "checks": checks}, {"id": cid, "from": "the map and derive.py (refs.resolved.json)"}


# ---- The values -------------------------------------------------------------------------------

_MISSING = object()


def pointer(doc, ptr: str, default=_MISSING):
    """RFC 6901 pointer; a negative index counts from the end of a list."""
    if ptr in ("", "/"):
        return doc
    cur = doc
    for raw in ptr.lstrip("/").split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        try:
            if isinstance(cur, list):
                cur = cur[int(key)]
            elif isinstance(cur, dict):
                cur = cur[key]
            else:
                raise KeyError(key)
        except (KeyError, IndexError, ValueError):
            if default is not _MISSING:
                return default
            fail(f"the pointer {ptr} does not resolve (at {key!r})")
    return cur


def value(spec, docs: dict) -> tuple[object, str]:
    """(the value, its provenance "source:/pointer[ ops]") of a value spec."""
    if isinstance(spec, str):
        spec = {"from": spec}
    if not isinstance(spec, dict) or not str(spec.get("from", "")).startswith("/"):
        fail(f"a value must be a pointer into a source, not {json.dumps(spec)[:80]}: the spec holds no value")
    name, _, rest = spec["from"].lstrip("/").partition("/")
    if name not in docs:
        fail(f"the value {spec['from']} names no source of this example ({', '.join(docs)})")
    v = pointer(docs[name], "/" + rest)
    if "where" in spec:
        v = [x for x in v if all(pointer(x, p, None) == want for p, want in spec["where"].items())]
    if "each" in spec:
        v = [pointer(x, spec["each"]) for x in v]
    if spec.get("distinct"):
        v = [x for i, x in enumerate(v) if i == 0 or x != v[i - 1]]
    if "slice" in spec:
        a, b = spec["slice"]
        v = v[a:b]
    if "at" in spec:
        v = v[spec["at"]]
    if "fields" in spec:
        # A list keeps the source's keys; a mapping {label: key} names each key for the reader.
        names = spec["fields"] if isinstance(spec["fields"], dict) else {f: f for f in spec["fields"]}
        # A key that starts with "/" is a pointer into the item.
        pick = lambda o: {label: pointer(o, key, None) if key.startswith("/") else o.get(key) for label, key in names.items()}  # noqa: E731
        v = [pick(o) for o in v] if isinstance(v, list) else pick(v)
    if spec.get("count"):
        v = len(v)
    elif spec.get("sha256"):
        v = sha(v)[:19]
    elif "lines" in spec:
        a, b = spec["lines"]
        v = "\n".join(str(v).splitlines()[a:b])
    ops = " ".join(f"{k}={json.dumps(spec[k], separators=(',', ':'))}" for k in spec if k != "from")
    return v, f"{name}:/{rest}" + (f" {ops}" if ops else "")


def fields_of(group: dict | None, docs: dict, prov: list[str]) -> list[dict]:
    out = []
    for label, spec in (group or {}).items():
        v, where = value(spec, docs)
        prov.append(where)
        out.append({"label": label, "value": v, "from": where})
    return out


def build_example(ex: dict, data: dict, repo: str, refs: dict | None, scratch: Scratch, keep: Path | None) -> dict:
    for key in ("id", "title", "sources", "steps"):
        if not ex.get(key):
            fail(f"an example needs {key}: {json.dumps(ex)[:80]}")
    docs, sources = {}, {}
    for name, src in ex["sources"].items():
        kind = src.get("kind")
        if kind not in KINDS:
            fail(f"{ex['id']}: source {name} has kind {kind!r}; use one of {', '.join(KINDS)}")
        commit = commit_of(repo, data, src.get("commit", "head")) if kind in ("run", "tlc", "vector") else data["head"]
        if kind == "run":
            doc, how = source_run(src, commit, scratch)
        elif kind == "tlc":
            doc, how = source_tlc(src, commit, scratch)
        elif kind == "vector":
            doc, how = source_vector(src, commit, scratch)
        elif kind == "controls":
            doc, how = source_controls(src, data, repo)
        else:
            doc, how = source_claim(src, data, refs)
        docs[name] = doc
        sources[name] = {"kind": kind, "commit": commit, **how, "sha256": sha(doc), "extracted_at": tm.now()}
        if keep:
            keep.mkdir(parents=True, exist_ok=True)
            (keep / f"{ex['id']}.{name}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    steps = []
    for n, st in enumerate(ex["steps"], start=1):
        if not st.get("name") or not st.get("reason"):
            fail(f"{ex['id']} step {n}: a step needs a name and a reason")
        prov: list[str] = []
        step = {"n": n, "station": st.get("station"), "name": st["name"], "in": fields_of(st.get("in"), docs, prov),
                "decision": fields_of(st.get("decision"), docs, prov), "out": fields_of(st.get("out"), docs, prov), "reason": st["reason"]}
        if st.get("diff"):
            d = st["diff"]
            # The path is a value (a pointer) or the label of a path that the values come from.
            spec_path = d.get("path", "")
            path, wp = value(spec_path, docs) if isinstance(spec_path, dict) or spec_path.startswith("/") else (spec_path, None)
            if "patch" in d:
                patch, w = value(d["patch"], docs)
                prov += [x for x in (wp, w) if x]
                step["diff"] = {"path": path, "patch": patch, "from": [x for x in (wp, w) if x]}
            else:
                before, wb = value(d["before"], docs)
                after, wa = value(d["after"], docs)
                prov += [x for x in (wp, wb, wa) if x]
                step["diff"] = {"path": path, "before": before, "after": after, "from": [x for x in (wp, wb, wa) if x]}
        if st.get("code"):
            step["code"] = {k: st["code"][k] for k in ("path", "symbol", "match", "context") if k in st["code"]}
        for check in st.get("assert", []):
            got, where = value(check["value"], docs)
            if got != check["equals"]:
                fail(f"{ex['id']} step {n} ({st['name']}): {where} is {json.dumps(got)[:120]}, the reason assumes {json.dumps(check['equals'])[:120]}")
        if not prov:
            fail(f"{ex['id']} step {n} ({st['name']}) shows no value from a source")
        step["provenance"] = list(dict.fromkeys(prov))
        steps.append(step)
    return {"id": ex["id"], "title": ex["title"], "diagram": ex.get("diagram"), "claims": ex.get("claims", []),
            "lead": ex.get("lead"), "sources": sources, "steps": steps}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--refs", help="refs.resolved.json (for a claim source); default: next to the map")
    ap.add_argument("--only", action="append", help="extract only this example id (repeatable); the others stay as they are")
    ap.add_argument("--keep-sources", action="store_true", help="write each source document to <out>.sources/")
    args = ap.parse_args()
    data = tm.load(args.map)
    spec = tm.load(args.spec)
    refs_path = Path(args.refs) if args.refs else Path(args.map).parent / "refs.resolved.json"
    refs = tm.load(refs_path) if refs_path.is_file() else None
    if refs and refs.get("head") != data["head"]:
        refs = None
    out = Path(args.out)
    old = {e["id"]: e for e in (tm.load(out).get("examples", []) if out.is_file() and args.only else [])}
    keep = out.with_suffix(".sources") if args.keep_sources else None
    scratch = Scratch(args.repo, data)
    try:
        examples = []
        for ex in spec.get("examples", []):
            if args.only and ex.get("id") not in args.only:
                if ex.get("id") in old:
                    examples.append(old[ex["id"]])
                continue
            examples.append(build_example(ex, data, args.repo, refs, scratch, keep))
            print(f"example {ex['id']}: {len(examples[-1]['steps'])} steps from {', '.join(f'{k} ({v['kind']})' for k, v in examples[-1]['sources'].items())}")
    finally:
        scratch.close()
    out.write_text(json.dumps({"schema": SCHEMA, "head": data["head"], "spec_sha256": sha(spec), "examples": examples},
                              indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(examples)} examples")
    return 0


if __name__ == "__main__":
    sys.exit(main())
