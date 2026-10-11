#!/usr/bin/env python3
"""Build the PR-body section and the explainer from a trust map.

    python3 scripts/explain.py --map trust-map.json --repo <git repo> --out DIR \
        [--extra explain.json] [--runtime REPO] [--explainer-url URL]

The explainer is a level ladder. Each level is one screen deep, and detail waits in collapsed
blocks, so a newcomer never meets an ID or a code name before the big picture:

  1 story       the merge verdict line (from the promises, the reviewer actions, the ready gates and the
                waivers); the ready checklist (when ready.json exists); the problem, the change and why to
                trust it; one before-and-after picture; one chip for each promise with its weakest verdict,
                and the verdict legend
  1a why        only with a journal: each user request as a short quote, linked to its claims, then
                the decisions that followed (what, why, evidence, result)
  2 loop        one diagram (direction "wrap" sets it in rows across a wide screen); five or six run
                steps, each tagged with its promise and with its code collapsed; the motion figure
                collapsed
  3 change      a before-and-after diagram and a "replaced by" table, both from git diff --numstat
  4 promises    one block per promise, weakest first: its chip label as the heading, its sentence, its
                strength, a reviewer action when it is weak; its claims collapsed, and the code, the
                checks and the controls collapsed under each claim
  5 verifiers   what caught the bug, missed the bug and cannot fail mean; the controls animation, the
                verifier map and the verifier table, each collapsed
  6 unclaimed   the changed code that no claim covers, from the diff and the claim code refs: the five
                riskiest files, then the rest collapsed
  7 tradeoffs   trade-offs, concerns and the verifications of this explainer
  8 exercises   a placeholder that the learning app fills
  9 glossary    each term that the page uses. A term in running text shows its definition on hover,
                focus or tap, and an abbreviation is spelled out at its first use

Writes DIR/pr-section.md, DIR/explainer.mdx (templates/three-level.mdx, filled) and one
self-contained MDX unit per level in DIR/chapters/NN-<name>.mdx.

The build stops (exit 1) when:
  - a claim, verifier or control ID, or a code name (backticked text, snake_case, CamelCase, a
    dotted module), is visible in levels 1-3 outside a table, a collapsed block or the Detailed
    mode of a diagram;
  - an ID, or the words "fact tier", is visible in the prose of levels 4, 5 and 7;
  - an architecture diagram lacks its `eli5` or its `detailed` mode, or the Detailed mode has
    more than 1.5 times the boxes of the ELI5 mode;
  - a claim is in no promise or in two, or a claim block or a link target is missing;
  - a weak promise (its weakest claim is not Proven) has no reviewer action;
  - the page uses a term (an acronym, a capitalised word inside a sentence, or a glossary term)
    that the glossary does not define;
  - a mechanical check gives a result that differs from the recorded one;
  - a code ref (scripts/coderef.py) resolves to no place, or to more than one, at the head;
  - an input (explain.json, the text fields of the map, the template) holds pasted code: 2 or more
    lines that are the same, after whitespace normalisation, as a tracked file at the head.

Every code excerpt, control diff and permalink comes from a code ref, never from typed text. A
codeRef is an anchor {"path", "symbol", "part"?, "match"?, "context"?} or, discouraged, a range
{"path", "start", "end"}. The resolved lines go to DIR/refs.resolved.json, not into the data.

--runtime is the Artifacture checkout. $UNDERSTANDO_VE_RUNTIME sets it too. The default asks the
visual-explainer CLI: `node ~/.claude/skills/visual-explainer/scripts/artifacture.mjs path`.

explain.json (written by the agent; strict STE) holds what the trust map does not:
  {"story": {"summary", "problem", "change", "trust", "picture": diagram name},
   "loop": {"intro", "diagram": diagram name,   five or six steps
            "steps": [{"text", "promise": promise id, "code"?: [codeRef]}],
            "walkthrough"?: {"title", "description", "nodes", "edges", "steps"}},   plain labels
   "change": {"intro", "areas": [{"id", "name", "paths": [path prefix], "replaced_by"?: area id,
                                   "note"?: str}],
              "diagrams"?: [diagram name]},
   "unclaimed": {"intro"?, "notes": {path: str}, "core"?: [path prefix]},   core files sort first
   "diagrams": {name: {"title", "description", "layout"?, "direction"?: "wrap",
                       "eli5": {"nodes", "edges"}, "detailed": {"nodes", "edges"}}},
   "control_walkthroughs": [{"title", "description", "controls": [control id]}],
   "risks": [{"claims": [claim id], "why", "fix"}],
   "tradeoffs": [str], "concerns": [str], "verifications": [str], "bullets": [str]}
Every entry in `diagrams` is an architecture diagram with two modes. The ELI5 mode has about four
to six boxes in plain words and plain-verb edges; the Detailed mode names the same boxes (the same
node ids) by their real modules and may add a few.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coderef  # noqa: E402
import mechanical  # noqa: E402
import tm  # noqa: E402

VERDICTS = ["Formal", "Proven", "Backed", "Asserted", "Gap"]
STRONG = ("Formal", "Proven")
MAX_SNIPPET = 30
LANG = {".py": "python", ".ts": "ts", ".tsx": "tsx", ".js": "js", ".mjs": "js", ".json": "json",
        ".md": "markdown", ".sh": "bash", ".toml": "toml", ".yml": "yaml", ".yaml": "yaml"}
CODE_EXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".jsx", ".sh", ".go", ".rs", ".java", ".kt",
            ".rb", ".swift", ".c", ".h", ".cc", ".cpp", ".cs", ".php", ".scala"}
TONE = {"Formal": "ok", "Proven": "ok", "Backed": "info", "Asserted": "warn", "Gap": "err"}
STATE_TONE = {"proven": "ok", "recorded": "info", "checked": "info", "cannot-fail": "err", "failing": "err", "broken": "err"}
FLAG_TONE = {"cannot-fail": "err", "control-missed": "warn", "same-family": "warn"}
KIND_GLYPH = {"type-pin": "rect", "boundary": "rect", "parity": "rect", "golden": "rect",
              "contract-format": "rect", "integration": "oval", "unit": "oval", "e2e": "oval",
              "eval": "oval", "measurement": "oval", "model": "diamond", "property": "oval", "fuzz": "oval",
              "contract": "rect", "static": "rect", "lean": "rect", "tla": "rect"}
GLYPH_FAMILY = {"rect": "static check", "oval": "run check", "diamond": "model judge"}
VISIBLE_UNCLAIMED = 5

# The one definition of each verdict. The glossary, the legend and every pill tooltip read it.
VERDICT_MEANING = {
    "Formal": "a proof or a model check backs the claim, a planted bug broke it, and a conformance run ties it to the code.",
    "Proven": "a check backs the claim, and a planted bug proved that the check can fail.",
    "Backed": "evidence backs the claim, but no planted bug proved that the check can fail, or the evidence is a recorded run that we did not run again.",
    "Asserted": "only the PR text says the claim. No check backs it.",
    "Gap": "no check backs the claim, and the PR text does not state it. You decide if it is important.",
}
# The three outcomes of a control, on the same tone scale as the verdicts.
OUTCOME = {
    "caught": ("Caught the bug", "ok", "the check failed on the planted bug. This is the good result: the check works."),
    "missed": ("Missed the bug", "warn", "the check passed on the planted bug. It did not find the bug."),
    "cannot-fail": ("Cannot fail", "err", "the check passed on each planted bug. It checks nothing that the bugs broke, so it backs no claim."),
}
TIER_WORD = {"fact": "a tool check, run again at the PR head", "guess": "a model judgment"}

# understando's own words. The page shows each one only when it uses it.
BUILTIN_GLOSSARY = [
    ("PR", "pull request: a set of changes that a team reviews before it merges them.", []),
    ("Claim", "one thing that the PR says is true about its code.", []),
    ("Promise", "a plain sentence that groups the claims about one property of the PR.", []),
    ("Verifier", "a check that backs a claim, for example a test, a type check or an eval.", ["check"]),
    ("Control", "a bug that we put in a scratch copy of the code on purpose, to see if a verifier finds it.", []),
    *((v, VERDICT_MEANING[v], []) for v in VERDICT_MEANING),
    ("Tier", "the rung of the strongest check that caught a planted bug: 1 an end-to-end test, 2 a property test, 3 a type or contract check, 4 a model check, 5 a proof.", []),
    ("Waived", "the author chose not to verify the claim, and wrote the reason.", []),
    ("Caught the bug", OUTCOME["caught"][2], ["caught"]),
    ("Missed the bug", OUTCOME["missed"][2], ["missed"]),
    ("Cannot fail", OUTCOME["cannot-fail"][2], ["cannot-fail"]),
    ("ID", "a short name, such as C05, for one claim, check or control.", []),
]
STOP_ACRONYMS = {"I", "A", "OK"}

ROW_OF_SKIP_KEYS = {"id", "from", "to", "edgeId", "tone", "shape", "layout", "href", "glyph", "stroke",
                    "status", "key", "kind", "width", "language", "style", "direction", "accent", "lane"}
SKIP_ATTRS = {"id", "href", "layout", "tone", "detailed", "language", "direction", "level", "definition", "meaning", "contains", "meta"}
CODE_LIKE = [
    (re.compile(r"`"), "backticked text"),
    (re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b"), "a snake_case name"),
    (re.compile(r"\b[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*\b"), "a CamelCase name"),
    (re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b"), "a camelCase name"),
    (re.compile(r"\b[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]{1,}\b"), "a dotted module or file name"),
    (re.compile(r"\w\(\)"), "a function call"),
    (re.compile(r"(?<![\w-])--[a-z]"), "a command-line flag"),
]


def fail(message: str) -> None:
    tm.fail("explain.py: " + message, 1)


def js(value) -> str:
    """A JSX expression that holds `value` as data, so MDX never parses it as markup.

    Escape < and > as \\u003c and \\u003e. JSON syntax holds them only inside strings, so the
    value does not change, and the MDX preflight never reads code text as a component tag."""
    text = json.dumps(value, ensure_ascii=False)
    return "{" + text.replace("<", "\\u003c").replace(">", "\\u003e") + "}"


# Reader words: a check "caught the bug" or "missed the bug", never "went red" or "stayed green".
# The trust map and the agent copy can use the test-runner words; the page never shows them.
READER_WORDS = [
    (re.compile(r"\bwent red on (?:the )?control (\w+)", re.I), r"caught the bug of control \1"),
    (re.compile(r"\bwent red on (a|the|each|one|every) (planted )?bug", re.I), r"caught \1 \2bug"),
    (re.compile(r"\b(?:went|turned) red\b", re.I), "caught the bug"),
    (re.compile(r"\bgoes red\b", re.I), "catches the bug"),
    (re.compile(r"\b(?:go|turn) red\b", re.I), "catch the bug"),
    (re.compile(r"\b(?:stayed|went|was) green\b", re.I), "missed the bug"),
    (re.compile(r"\bstays green\b", re.I), "misses the bug"),
    (re.compile(r"\bstay green\b", re.I), "miss the bug"),
]


def reader(text: str) -> str:
    for pattern, words in READER_WORDS:
        text = pattern.sub(words, text)
    return text


class Terms:
    """The glossary terms in running text. The first use in each level becomes a Term (a tooltip
    with the definition); the first use on the page of an abbreviation also spells it out."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, str, str | None, list[str]]] = []
        self.pattern: re.Pattern | None = None
        self.level_seen: set[str] = set()
        self.page_expanded: set[str] = set()
        self.enabled = True

    def load(self, glossary: list[tuple[str, str]], aliases: dict[str, list[str]]) -> None:
        self.entries = [(t, m, expansion(t, m), aliases.get(t, [])) for t, m in glossary]
        forms = sorted({f for t, _, _, al in self.entries for f in [t, *al] if len(f) >= 2}, key=len, reverse=True)
        if not forms:
            return
        alts = "|".join(re.escape(f) for f in forms)
        self.pattern = re.compile(rf"(?<![\w-])({alts})(?:s|es)?(?![\w-])", re.I)

    def level(self) -> None:
        self.level_seen = set()

    def find(self, word: str):
        w = norm(word)
        for t, m, e, al in self.entries:
            for f in [t, *al]:
                if (f == word) if is_acronym(f) else (f.lower() == word.lower() or norm(f) == w):
                    return t, m, e
        return None

    def render(self, text: str) -> str:
        if not self.pattern or not text or not self.enabled:
            return js(text) if text else ""
        out, last = [], 0
        for m in self.pattern.finditer(text):
            hit = self.find(m.group(1))
            if not hit or hit[0] in self.level_seen:
                continue
            term, meaning, exp = hit
            # An alias (such as "UAP plan") shows the tooltip but leaves the spelled-out first use to the term itself.
            if m.group(1) == term or not exp or term in self.page_expanded:
                self.level_seen.add(term)
            if m.start() > last:
                out.append(js(text[last:m.start()]))
            attrs = f"definition={js(term + ': ' + meaning)}"
            if exp and term not in self.page_expanded and m.group(1) == term:
                self.page_expanded.add(term)
                attrs += f" expansion={js(exp)}"
            out.append(f"<Term {attrs}>{js(m.group(0))}</Term>")
            last = m.end()
        if last < len(text):
            out.append(js(text[last:]))
        return "".join(out)


def is_acronym(term: str) -> bool:
    return re.fullmatch(r"[0-9]*[A-Z][A-Z0-9]*(?:-[0-9A-Z]+)*", term) is not None


def expansion(term: str, meaning: str) -> str | None:
    """The full words of an abbreviation: the first clause of its meaning, when it is a short name."""
    if not is_acronym(term):
        return None
    head = re.split(r"[.:;,]", meaning, maxsplit=1)[0].strip()
    words = head.split()
    if not words or len(words) > 5 or words[0].lower() in ("a", "an", "the") or head.lower() == term.lower():
        return None
    return head


TERMS = Terms()


def inline(text: str, terms: bool = True) -> str:
    """JSX for STE text. A `backtick` span becomes code; everything else stays a string expression,
    with reader words, and with a Term at the first use of a glossary term in the level."""
    out = []
    for i, part in enumerate(text.split("`")):
        if part:
            out.append(f"<code>{js(part)}</code>" if i % 2 else (TERMS.render(reader(part)) if terms else js(reader(part))))
    return "".join(out)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def claim_anchor(cid: str) -> str:
    return f"claim-{slug(cid)}"


def promise_anchor(pid: str) -> str:
    return f"promise-{slug(pid)}"


def git(repo: str, *args: str) -> str:
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if out.returncode != 0:
        fail(f"git {' '.join(args[:2])} failed: {out.stderr.strip()}")
    return out.stdout


RESOLVED: dict[str, coderef.Resolved] = {}


def snippet(repo: str, head: str, ref: dict, slug: str | None = None) -> tuple[str, int, int, str | None]:
    """(code, start, end, permalink) of a code ref at the head. The build copies the code; nobody
    types it. A ref that resolves to no place, or to more than one, stops the build."""
    try:
        r = coderef.resolve(repo, head, ref)
    except coderef.AnchorError as exc:
        fail(f"a code ref does not resolve at the head: {exc}. Fix the ref (understando snippet), then build again.")
    RESOLVED[coderef.ref_key(ref)] = r
    return r.excerpt, r.start, r.end, coderef.permalink(repo, head, ref["path"], r.start, r.end, slug)


def code_block(repo: str, data: dict, ref: dict) -> str:
    text, start, end, link = snippet(repo, data["head"], ref, data.get("repo"))
    name = f"{ref['path']}:{start}" + (f"-{end}" if end != start else "")
    out = f"<CodeBlock language={js(LANG.get(Path(ref['path']).suffix, 'text'))} filename={js(name)} code={js(text)} />"
    if link:
        out += f"\n<p><a href={js(link)}>{js('Open these lines at the PR head')}</a></p>"
    return out


def runtime_path(explicit: str | None) -> str:
    """The Artifacture checkout: --runtime, then $UNDERSTANDO_VE_RUNTIME, then the visual-explainer CLI."""
    if explicit:
        return explicit
    if os.environ.get("UNDERSTANDO_VE_RUNTIME"):
        return os.environ["UNDERSTANDO_VE_RUNTIME"]
    cli = Path.home() / ".claude/skills/visual-explainer/scripts/artifacture.mjs"
    out = subprocess.run(["node", str(cli), "path"], capture_output=True, text=True)
    if out.returncode != 0:
        tm.fail("cannot resolve the Artifacture runtime; pass --runtime")
    return out.stdout.strip().splitlines()[-1]


# ---- The diff --------------------------------------------------------------------------------

class Diff:
    """git diff --numstat and the added line numbers from the base to the head."""

    def __init__(self, repo: str, base: str, head: str):
        self.repo = repo
        self.files: dict[str, tuple[int, int]] = {}
        for line in git(repo, "diff", "--numstat", "--no-renames", base, head).splitlines():
            a, d, path = line.split("\t", 2)
            if a != "-":
                self.files[path] = (int(a), int(d))
        self.deleted = set(git(repo, "diff", "--name-only", "--no-renames", "--diff-filter=D", base, head).split())
        self.created = set(git(repo, "diff", "--name-only", "--no-renames", "--diff-filter=A", base, head).split())
        self.added_lines: dict[str, set[int]] = {}
        current = None
        for line in git(repo, "diff", "-U0", "--no-renames", base, head).splitlines():
            if line.startswith("+++ "):
                current = None if line == "+++ /dev/null" else line[6:]
                if current:
                    self.added_lines.setdefault(current, set())
            elif line.startswith("@@") and current:
                m = re.search(r"\+(\d+)(?:,(\d+))?", line)
                start, count = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
                self.added_lines[current].update(range(start, start + count))
        code = [p for p in self.files if is_code(p)]
        common = os.path.commonpath(code) if len(code) > 1 else ""
        self.root = common + "/" if common else ""

    def short(self, path: str) -> str:
        return path[len(self.root):] if self.root and path.startswith(self.root) else path

    def under(self, prefixes: list[str]) -> list[str]:
        return [p for p in self.files if any(p == x or p.startswith(x.rstrip("/") + "/") for x in prefixes)]


def is_test(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    return (any(p in ("tests", "test", "__tests__", "spec") for p in parts[:-1]) or name.startswith("test_")
            or re.search(r"(_test|\.test|\.spec)\.\w+$", name) is not None)


def is_code(path: str) -> bool:
    return Path(path).suffix in CODE_EXT and not is_test(path)


def lines(n: int, sign: str) -> str:
    return f"{sign}{n:,}" if n else "0"


# ---- Shared pieces ---------------------------------------------------------------------------

def definitions(items, size: str | None = None) -> str:
    """A DefinitionList of (term, STE text, tone or None[, raw]). With raw, the text is JSX already."""
    body = "".join(f"<Definition term={js(term)}" + (f" tone=\"{tone}\"" if tone else "") + f">{text if raw else inline(text)}</Definition>"
                   for term, text, tone, raw in ((*i, False) if len(i) == 3 else i for i in items))
    return f"<DefinitionList{f' size={js(size)}' if size else ''}>{body}</DefinitionList>"


def subsection(anchor: str | None, title: str, body: str, level: int = 3, marker: str | None = None, share: bool = False) -> str:
    attrs = (f" id={js(anchor)}" if anchor else "") + (f" level={{{level}}}" if level != 3 else "") + (f" marker={js(marker)}" if marker else "") + (" share" if share else "")
    return f"<Subsection{attrs} title={title}>\n{body}\n</Subsection>"


def disclosure(summary: str, body: str, anchor: str | None = None, meta: str | None = None, jsx: bool = False,
               share: bool = False, lazy: bool = False, contains: list[str] | None = None) -> str:
    """A collapsed block. `summary` is plain text (a string expression) unless jsx is True. A lazy
    block renders its body at the first open; `contains` lists the link targets inside it."""
    attrs = (f" id={js(anchor)}" if anchor else "") + f" summary={summary if jsx else js(summary)}" + (f" meta={js(meta)}" if meta else "")
    attrs += (" share" if share else "") + (" lazy" if lazy else "") + (f" contains={js(contains)}" if contains else "")
    return f"<Disclosure{attrs}>\n{body}\n</Disclosure>"


def para(text: str) -> str:
    return f"<p>{inline(text)}</p>"


def next_link(target: str, text: str) -> str:
    """The way on: a link to the next level, so the reader always knows where to go."""
    return f"<p>{js('Next: ')}<a href={js('#' + target)}>{js(text)}</a>{js('.')}</p>"


def none(text: str) -> str:
    return f"<p><em>{js(text)}</em></p>"


def table(columns: list[dict], rows: list[dict], label: str) -> str:
    return f"<DataTable label={js(label)} columns={js(columns)} rows={js(rows)} />"


def compact_table(columns: list[dict], rows: list[dict], label: str) -> str:
    return f"<DataTable density=\"compact\" label={js(label)} columns={js(columns)} rows={js(rows)} />"


def pill(verdict: str) -> str:
    return f"<StatusPill tone=\"{TONE[verdict]}\" meaning={js(verdict + ': ' + VERDICT_MEANING[verdict])}>{js(verdict)}</StatusPill>"


def verdict_legend(data: dict, anchor: str | None = None) -> str:
    """The four verdicts (and Formal, when the page uses it), each a swatch, its word and its meaning."""
    used = {c["verdict"] for c in data["claims"]}
    items = [{"label": v, "tone": TONE[v], "detail": VERDICT_MEANING[v][0].upper() + VERDICT_MEANING[v][1:]}
             for v in VERDICTS if v != "Formal" or v in used]
    body = f"<Legend layout=\"list\" title={js('What each verdict means')} items={js(items)} />"
    return f"<div id={js(anchor)}>{body}</div>" if anchor else body


def weakest(verdicts) -> str | None:
    found = [v for v in verdicts if v]
    return max(found, key=VERDICTS.index) if found else None


def tally(verdicts: list[str]) -> str:
    return ", ".join(f"{verdicts.count(v)} {v}" for v in VERDICTS if v in verdicts)


def modes_block(name: str, spec: dict) -> str:
    """One architecture diagram in its ELI5 (Simple) and Detailed modes."""
    for mode in ("eli5", "detailed"):
        if not (spec.get(mode) or {}).get("nodes"):
            fail(f"diagram {name!r} has no {mode} mode; each architecture diagram needs eli5 and detailed nodes and edges")
    simple, detailed = spec["eli5"], spec["detailed"]
    direction = f" direction={js(spec['direction'])}" if spec.get("direction") else ""
    missing = {n["id"] for n in simple["nodes"]} - {n["id"] for n in detailed["nodes"]}
    if missing:
        fail(f"diagram {name!r}: the eli5 nodes {sorted(missing)} have no detailed node with the same id")
    if len(detailed["nodes"]) > math.ceil(1.5 * len(simple["nodes"])):
        fail(f"diagram {name!r}: {len(detailed['nodes'])} detailed nodes for {len(simple['nodes'])} eli5 nodes; keep it at 1.5 times or less")
    for node in simple["nodes"]:
        for text in (node.get("label", ""), node.get("detail", "")):
            hit = code_like(text)
            if hit:
                fail(f"diagram {name!r}: the eli5 node {node['id']!r} has {hit}: {text!r}")
    for edge in simple["edges"]:
        hit = code_like(edge.get("label", ""))
        if hit:
            fail(f"diagram {name!r}: an eli5 edge label has {hit}: {edge['label']!r}")
    graph = lambda g: {k: g[k] for k in ("nodes", "edges", "legend") if k in g}  # noqa: E731
    layout = spec.get("layout", "flow")
    return (f"<DiagramModes layout={js(layout)}{direction} title={js(spec['title'])} description={js(spec['description'])} "
            f"simple={js(graph(simple))} detailed={js(graph(detailed))} />")


def code_like(text: str) -> str | None:
    for pattern, what in CODE_LIKE:
        if pattern.search(text):
            return what
    return None


# ---- Level 1: the story ----------------------------------------------------------------------

def promises_in_order(data: dict) -> list[tuple[dict, str, list[str]]]:
    """Each promise with its strength and its claims, weakest first; ties keep the map order."""
    verdict_of = {c["id"]: c["verdict"] for c in data["claims"]}
    rows = []
    for p in data["promises"]:
        cids = sorted(p["claims"], key=lambda c: (-VERDICTS.index(verdict_of[c]), c))
        rows.append((p, weakest(verdict_of[c] for c in cids), cids))
    return sorted(rows, key=lambda r: -VERDICTS.index(r[1]))


def ready_block(ready: dict) -> str:
    """The ready checklist at the top of the page. Gate details are plain; the items with IDs stay collapsed."""
    gates = definitions((f"Gate {g['n']}: {g['name']}", ("Pass. " if g["pass"] else "Fail. ") + g["detail"], "ok" if g["pass"] else "err")
                        for g in ready["gates"])
    items = [f"<li>{js(f'Gate {g[chr(110)]}: ' + item)}</li>" for g in ready["gates"] for item in g.get("items", [])]
    body = para("Four gates decide if the PR is ready to review. Each gate passes or fails.") + "\n" + gates
    if items:
        body += "\n" + disclosure("Show what each gate found", "<ul>" + "".join(items) + "</ul>")
    return subsection("story-ready", js("Ready checklist"), body)


def merge_verdict(data: dict, ready: dict | None = None) -> tuple[str, list[dict]]:
    """Can the reviewer merge? From the data only: a promise at Gap or Asserted with a reviewer
    action blocks, unless each of its weak claims is waived; a failed ready gate blocks; a Backed
    promise with a reviewer action, and a waived claim, are risks to accept.
    Returns ("not-ready" | "accept" | "ready", items); each item has text, href and kind."""
    claims = {c["id"]: c for c in data["claims"]}
    blocking, accept = [], []
    for g in (ready or {}).get("gates", []):
        if not g["pass"]:
            blocking.append({"label": f"Gate {g['n']}, {g['name']}", "text": g["detail"], "href": "#story-ready"})
    for p, strength, cids in promises_in_order(data):
        action = p.get("reviewer_action")
        weak = [claims[c] for c in cids if claims[c]["verdict"] in ("Gap", "Asserted")]
        href = "#" + promise_anchor(p["id"])
        if strength in ("Gap", "Asserted") and action and not all(c.get("waiver") for c in weak):
            blocking.append({"label": p["label"], "text": first_sentence(action), "href": href})
        elif action and strength != "Proven" and strength != "Formal":
            accept.append({"label": p["label"], "text": first_sentence(action), "href": href})
        for c in weak:
            if c.get("waiver"):
                accept.append({"label": p["label"], "text": "Waived: " + c["waiver"]["reason"], "href": "#" + claim_anchor(c["id"])})
    if blocking:
        return "not-ready", blocking
    return ("accept", accept) if accept else ("ready", [])


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]


MERGE_WORDS = {"not-ready": ("Not ready", "err", "Do these first:"),
               "accept": ("Ready if you accept", "warn", "these risks:"),
               "ready": ("Ready", "ok", "Each promise is Proven, and no gate fails.")}
MAX_MERGE_ITEMS = 3


def verdict_line(data: dict, ready: dict | None) -> str:
    """The merge answer, first on the page: a state word and up to three items, each a link to its promise."""
    form, items = merge_verdict(data, ready)
    word, tone, lead = MERGE_WORDS[form]
    head = f"<p data-merge-verdict={js(form)}><StatusPill tone=\"{tone}\">{js(word)}</StatusPill>{js(' ' + lead)}</p>"
    if not items:
        return head
    shown, rest = items[:MAX_MERGE_ITEMS], items[MAX_MERGE_ITEMS:]
    rows = "".join(f"<li><a href={js(i['href'])}>{js(i['label'])}</a>{js(': ')}{inline(i['text'])}</li>" for i in shown)
    tail = ""
    if rest:
        tail = f"\n<p>{js(f'And {len(rest)} more: ')}" + js(", ").join(f"<a href={js(i['href'])}>{js(i['label'])}</a>" for i in rest) + f"{js('.')}</p>"
    return head + "\n{<ol data-merge-items>" + rows + "</ol>}" + tail


def story(data: dict, extra: dict, glossary_used: list[tuple[str, str]], ready: dict | None = None, next_level: str = "loop") -> str:
    s = extra.get("story") or {}
    parts = [subsection("story-verdict", js("Can you merge it?"), verdict_line(data, ready))]
    if ready:
        parts.append(ready_block(ready))
    ideas = [("The problem", s.get("problem")), ("The change", s.get("change")), ("Why you can trust it", s.get("trust"))]
    if any(text for _, text in ideas):
        parts.append(definitions(((term, text, None) for term, text in ideas if text), size="lead"))
    else:
        parts.append(none("This explainer has no story yet. The explain step writes it in explain.json."))
    if s.get("picture"):
        parts.append(modes_block(s["picture"], diagram(extra, s["picture"])))
    chips = [{"label": p["label"], "href": "#" + promise_anchor(p["id"]), "tone": TONE[strength], "status": strength,
              "meaning": strength + ": " + VERDICT_MEANING[strength]}
             for p, strength, _ in promises_in_order(data)]
    parts.append(subsection("story-promises", js("What the PR promises"),
                            para("Each chip is one promise. The pill shows its weakest claim: the promise is only as strong as that claim. Select a chip to see the proof.")
                            + f"\n<ChipLinks label={js('The promises, weakest first')} items={js(chips)} />\n" + verdict_legend(data, "story-legend")))
    if next_level == "why":
        parts.append(next_link("why", "see why it was built this way"))
    else:
        parts.append(next_link("loop", "see one run of the change, step by step"))
    return "\n".join(parts)


# ---- Level 1a: why it was built this way -----------------------------------------------------

QUOTE_WORDS = 30
ASKED: dict[str, int] = {}


def load_journal(path: str | None) -> list[dict]:
    if not path or not Path(path).is_file():
        return []
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def short_quote(text: str) -> str:
    words = text.split()
    return " ".join(words[:QUOTE_WORDS]) + (" ..." if len(words) > QUOTE_WORDS else "")


def why_level(data: dict, journal: list[dict]) -> str | None:
    """The user's intent, from the journal: each request as a short quote, with the claims it asked for.

    The quotes are the user's words, so the STE lint skips them (data-quote). The rest is strict STE."""
    prompts = [r for r in journal if r.get("kind") == "prompt"]
    invariants = [i for i in data.get("invariants", []) if i["status"] in ("accepted", "proposed")]
    if not prompts and not invariants:
        return None
    claims = {c["id"]: c for c in data["claims"]}
    parts = [para("This level shows what the user asked for, in order, in the user's own words. Each request links to the claims that it asked for. Then the decisions that followed show what was chosen and why.")]
    # The requests are numbered steps (two columns on a wide screen), so the level fits one screen.
    steps = []
    for i, r in enumerate(prompts, 1):
        linked = [cid for cid in r.get("claims", []) if cid in claims]
        for cid in linked:
            ASKED.setdefault(cid, i)
        body = f"<blockquote data-quote=\"user\"><p>{js(short_quote(r.get('what') or r.get('text', '')))}</p></blockquote>"
        if linked:
            links = "".join(f"<li><a href={js('#' + claim_anchor(cid))}>{js((claims[cid].get('plain') or {}).get('what', claims[cid]['text']) + ' (' + cid + ')')}</a></li>" for cid in linked)
            body += disclosure(f"Show the claims that this request asked for ({len(linked)})", "<ul>" + links + "</ul>")
        else:
            body += f"<p><em>{js('No claim links to this request.')}</em></p>"
        steps.append(f"<Step id={js(f'why-{i}')}>{body}</Step>")
    if steps:
        parts.append(f"{{<Steps label={js('The requests, in order')}>" + "".join(steps) + "</Steps>}")
    if invariants:
        rows = "".join(f"<li>{js(('Confirmed by the user: ' if i['author'] == 'user' and i['status'] == 'accepted' else 'Proposed, not confirmed: ') + i['text'])}</li>"
                       for i in invariants)
        parts.append(subsection("why-invariants", js("The invariants"),
                                para("An invariant is a rule that must always hold. Only a rule that the user confirmed can make a claim Proven or Formal.")
                                + "\n" + disclosure(f"Show the {len(invariants)} invariants", "<ul>" + rows + "</ul>")))
    decisions = [r for r in journal if r.get("kind") in ("decision", "verifier-choice", "waiver", "result")]
    if decisions:
        def row(r: dict) -> str:
            cells = [r.get("what") or r.get("text", "")] + [f"{k.capitalize()}: {r[k]}" for k in ("why", "evidence", "result") if r.get(k)]
            if r.get("claims"):
                cells.append("Claims: " + ", ".join(r["claims"]))
            return f"<li>{js(r['kind'] + '. ' + ' '.join(cells))}</li>"
        parts.append(disclosure(f"Show the {len(decisions)} decisions that followed", "<ul>" + "".join(row(r) for r in decisions) + "</ul>", anchor="why-decisions"))
    parts.append(next_link("loop", "see one run of the change, step by step"))
    return "\n".join(parts)


def diagram(extra: dict, name: str) -> dict:
    spec = (extra.get("diagrams") or {}).get(name)
    if not spec:
        fail(f"explain.json names the diagram {name!r}, but `diagrams` has no entry for it")
    return spec


# ---- Level 2: the loop -----------------------------------------------------------------------

def loop(data: dict, extra: dict, repo: str) -> str:
    spec = extra.get("loop") or {}
    labels = {p["id"]: p["label"] for p in data["promises"]}
    parts = [para(spec["intro"])] if spec.get("intro") else []
    if spec.get("diagram"):
        parts.append(modes_block(spec["diagram"], diagram(extra, spec["diagram"])))
    steps = spec.get("steps") or []
    if not steps:
        parts.append(none("This explainer has no run steps yet. The explain step writes them in explain.json."))
    items = []
    for i, step in enumerate(steps, 1):
        pid = step.get("promise")
        if pid not in labels:
            fail(f"loop step {i} names the promise {pid!r}, which the map does not have")
        body = f"<p>{inline(step['text'])}{js(' ')}<a href={js('#' + promise_anchor(pid))}>{js('Promise: ' + labels[pid])}</a></p>"
        if len(steps) > 6:
            fail(f"the loop has {len(steps)} steps; keep it at five or six, so the level fits one screen")
        code = [code_block(repo, data, ref) for ref in step.get("code", [])]
        if code:
            body += "\n" + disclosure("Show the code for this step", "\n".join(code), lazy=True)
        items.append(f"<Step id={js(f'loop-step-{i}')}>{body}</Step>")
    if items:
        # A JSX expression keeps the list one block, so MDX never splits a step at a line break.
        parts.append(f"{{<Steps label={js('The steps of one run')}>" + "".join(items) + "</Steps>}")
    motion = spec.get("walkthrough")
    if motion:
        legend = glyph_legend(motion, SHAPE_NAMES)
        parts.append(disclosure("Show the motion: " + motion["title"][0].lower() + motion["title"][1:], para(motion["description"]) + "\n" +
                                f"<DiagramWalkthrough layout=\"flow\" title={js(motion['title'])} description={js(motion['description'])} "
                                f"nodes={js(motion['nodes'])} edges={js(motion['edges'])} steps={js(motion['steps'])} legend={js(legend)} />",
                                anchor="loop-motion", lazy=True))
    parts.append(next_link("change", "see what the PR deletes and adds"))
    return "\n".join(parts)


SHAPE_NAMES = {"rect": "step", "oval": "input or result", "diamond": "decision"}


def glyph_legend(spec: dict, names: dict[str, str]) -> list[dict]:
    glyphs = sorted({n.get("shape", "rect") for n in spec["nodes"]}, key=["rect", "oval", "diamond", "dot"].index)
    return [{"label": names.get(g, g), "glyph": g} for g in glyphs if g in names]


# ---- Level 3: what changed -------------------------------------------------------------------

def change(data: dict, extra: dict, diff: Diff) -> str:
    spec = extra.get("change") or {}
    areas = spec.get("areas") or []
    by_id = {a["id"]: a for a in areas}
    for a in areas:
        if a.get("paths") and not diff.under(a["paths"]):
            fail(f"change area {a['id']!r}: no changed file is under {a['paths']}")
        if a.get("replaced_by") and a["replaced_by"] not in by_id:
            fail(f"change area {a['id']!r}: replaced_by names {a['replaced_by']!r}, which is not an area")
    parts = [para(spec.get("intro") or "The diagram groups the changed files. The table lists each file that the PR deletes, with the lines it removes and what takes its place.")]
    parts.append(subsection("change-diagram", js("Before and after"), modes_block("before and after (from the diff)", change_diagram(areas, diff))))

    owner = area_owner(areas, diff)
    rows = []
    for a in areas:
        if not a.get("replaced_by") and not a.get("note"):
            continue
        target = a.get("note") or by_id[a["replaced_by"]]["name"]
        files = [p for p, aid in owner.items() if aid == a["id"]]
        if a.get("rollup"):
            prefix = ", ".join(diff.short(x) for x in a["paths"])
            removed = sum(diff.files[p][1] for p in files)
            rows.append({"cells": {"file": {"text": f"{prefix} ({len(files)} files)"}, "removed": lines(removed, "-"), "by": target}})
            continue
        gone = sorted((p for p in files if p in diff.deleted and is_code(p) and diff.files[p][1] >= 100), key=lambda p: -diff.files[p][1])
        rows += [{"cells": {"file": {"text": diff.short(p)}, "removed": lines(diff.files[p][1], "-"), "by": target}} for p in gone]
    rows.sort(key=lambda r: -int(r["cells"]["removed"].lstrip("-").replace(",", "")))
    if not areas:
        gone = sorted((p for p in diff.deleted if is_code(p)), key=lambda p: -diff.files[p][1])
        rows = [{"cells": {"file": {"text": diff.short(p)}, "removed": lines(diff.files[p][1], "-"), "by": "Not stated"}} for p in gone]
    columns = [{"key": "file", "label": "Deleted or replaced", "kind": "id", "width": "20rem"},
               {"key": "removed", "label": "Lines removed", "kind": "number", "width": "8rem"},
               {"key": "by", "label": "Replaced by"}]
    body = table(columns, rows, "Deleted or replaced code") if rows else none("The PR deletes no code file.")
    parts.append(subsection("change-table", js("What the PR deletes, and what replaces it"), body))
    for name in spec.get("diagrams") or []:
        d = diagram(extra, name)
        parts.append(subsection("change-" + slug(name), js(d["title"]), para(d["description"]) + "\n" + modes_block(name, d)))
    parts.append(next_link("promises", "check each promise, weakest first"))
    return "\n".join(parts)


def area_owner(areas: list[dict], diff: Diff) -> dict[str, str]:
    """Each changed file and the area with the longest path prefix that holds it."""
    owner: dict[str, tuple[int, str]] = {}
    for a in areas:
        for prefix in a.get("paths", []):
            for p in diff.under([prefix]):
                if len(prefix) > owner.get(p, (-1, ""))[0]:
                    owner[p] = (len(prefix), a["id"])
    return {p: aid for p, (_, aid) in owner.items()}


def change_diagram(areas: list[dict], diff: Diff) -> dict:
    """The before-and-after diagram, built from the diff: plain area names in the ELI5 mode, the
    paths in the Detailed mode."""
    owner = area_owner(areas, diff)

    def count(a: dict) -> tuple[int, int, int]:
        files = [p for p, aid in owner.items() if aid == a["id"]]
        return sum(diff.files[p][0] for p in files), sum(diff.files[p][1] for p in files), len(files)

    if not areas:
        gone = [p for p in diff.deleted if is_code(p)]
        new = [p for p in diff.created if is_code(p)]
        nodes, edges = [], []
        if gone:
            nodes.append({"id": "gone", "label": "Deleted code", "detail": f"{lines(sum(diff.files[p][1] for p in gone), '-')} lines in {len(gone)} files"})
        if new:
            nodes.append({"id": "new", "label": "New code", "detail": f"{lines(sum(diff.files[p][0] for p in new), '+')} lines in {len(new)} files"})
        if gone and new:
            edges.append({"from": "gone", "to": "new", "label": "replaced by"})
        if not nodes:
            nodes = [{"id": "edits", "label": "Edits to existing code", "detail": f"{len(diff.files)} files"}]
        detail_nodes = [{**n, "label": n["label"] + " (" + ", ".join(diff.short(p) for p in sorted(gone if n["id"] == "gone" else new)[:3]) + ")"} if n["id"] in ("gone", "new") else n for n in nodes]
        return {"title": "Before and after", "description": "The code that the PR deletes and the code that it adds.",
                "eli5": {"nodes": nodes, "edges": edges}, "detailed": {"nodes": detail_nodes, "edges": edges}}
    nodes, detail_nodes, edges = [], [], []
    for a in areas:
        added, removed, n = count(a)
        before = bool(a.get("replaced_by") or a.get("note"))
        size = f"{lines(removed, '-')} lines" if before else f"{lines(added, '+')} lines"
        node = {"id": a["id"], "label": a["name"], **({"detail": size} if a.get("paths") else {}),
                **({"shape": "oval"} if not a.get("paths") else {})}
        nodes.append(node)
        short = [diff.short(p) for p in a.get("paths", [])]
        label = ", ".join(short[:3]) + (f" and {len(short) - 3} more" if len(short) > 3 else "")
        detail_nodes.append({**node, "label": label or a["name"]})
        if a.get("replaced_by"):
            edges.append({"from": a["id"], "to": a["replaced_by"], "label": "replaced by"})
    return {"title": "Before and after", "description": "Each box is a group of changed files, with its line count from the diff. An arrow points from deleted code to the code that replaces it.",
            "eli5": {"nodes": nodes, "edges": edges}, "detailed": {"nodes": detail_nodes, "edges": edges}}


# ---- Level 4: the promises -------------------------------------------------------------------

def promises(data: dict, extra: dict, repo: str) -> str:
    claims = {c["id"]: c for c in data["claims"]}
    risks = {cid: r for r in extra.get("risks") or [] for cid in r["claims"]}
    by_claim: dict[str, list[dict]] = {}
    for v in data["verifiers"]:
        for cid in v["claims"]:
            by_claim.setdefault(cid, []).append(v)
    controls: dict[str, list[dict]] = {}
    for k in data["controls"]:
        controls.setdefault(k["verifier"], []).append(k)
    parts = [para("Each promise below is a plain sentence about the PR. Its strength is the verdict of its weakest claim. The weakest promises come first. Open a promise to see its claims, then open a claim to see its code, its checks and the bugs that we planted.")
             + f"<p><a href={js('#story-legend')}>{js('See what each verdict means')}</a></p>"]
    for i, (p, strength, cids) in enumerate(promises_in_order(data), 1):
        verdicts = [claims[c]["verdict"] for c in cids]
        word = "claim" if len(cids) == 1 else "claims"
        head = para(p["sentence"]) + f"<p><strong>{js(strongest_tier(claims[c] for c in cids))}</strong></p>"
        head += f"<p>{pill(strength)}{js(f' This is the verdict of its weakest claim. Its {len(cids)} {word}: {tally(verdicts)}.')}</p>"
        waived = [claims[c] for c in cids if claims[c].get("waiver")]
        if waived:
            head += "".join(f"<p>{js('Waived: ' + (c.get('plain') or {}).get('what', c['text']) + ' Reason: ' + c['waiver']['reason'])}</p>" for c in waived)
        lines_ = []
        action = p.get("reviewer_action")
        if strength != "Proven" and not action:
            fail(f"promise {p['id']} is {strength}, so it needs a reviewer_action")
        if action:
            lines_.append(("Reviewer action", action, "warn" if strength != "Proven" else None))
        for cid in cids:
            if cid in risks and claims[cid]["verdict"] != "Proven":
                fix = risks[cid].get("fix")
                if fix:
                    lines_.append(("Cheapest fix", inline(fix) + js(" ") + f"<a href={js('#' + claim_anchor(cid))}>{js('Open the claim')}</a>", None, True))
        body = [head] + ([definitions(lines_)] if lines_ else [])
        blocks = [claim_block(claims[c], risks.get(c), by_claim.get(c, []), controls, data, repo) for c in cids]
        body.append(disclosure(f"Show the {len(cids)} {word} behind this promise", "\n".join(blocks), anchor=promise_anchor(p["id"]) + "-claims"))
        parts.append(subsection(promise_anchor(p["id"]), js(p["label"]), "\n".join(body), marker=str(i), share=True))
    parts.append(next_link("verifiers", "see how we tested the checks"))
    return "\n".join(parts)


def strongest_tier(claims) -> str:
    """The first line of a promise: the strongest rung that a planted bug proved, over its claims."""
    tiers = [c.get("tier") for c in claims if c.get("tier")]
    if not tiers:
        return "Strongest check: none. No check of this promise caught a planted bug."
    t = max(tiers)
    return f"Strongest check: tier {t}, {tm.LADDER_NAMES[t]}."


def claim_block(c: dict, risk: dict | None, verifiers: list[dict], controls: dict[str, list[dict]], data: dict, repo: str) -> str:
    plain = c.get("plain") or {"what": c["text"], "proof": c["reason"]}
    terms = [("How it is proven", plain["proof"], None)]
    if plain.get("warning"):
        terms.append(("Warning", plain["warning"], "warn"))
    if risk and c["verdict"] != "Proven":
        terms.append(("Why it is weak", risk["why"], "warn"))
        if risk.get("fix"):
            terms.append(("Cheapest fix", risk["fix"], None))
    terms.append(("Verdict", f"{c['verdict']}. {c['reason']}", None))
    if c.get("tier"):
        terms.append(("Tier", f"{c['tier']}: {tm.LADDER_NAMES[c['tier']]}.", None))
    if c.get("waiver"):
        terms.append(("Waived", c["waiver"]["reason"], "warn"))
    terms.append(("Source", c["source"], None))
    inv = next((i for i in data.get("invariants", []) if i["id"] == c.get("invariant")), None)
    if inv:
        confirmed = inv["author"] == "user" and inv["status"] == "accepted"
        terms.append(("Invariant", ("Confirmed by the user: " if confirmed else "Proposed, not confirmed by the user: ") + inv["text"],
                      None if confirmed else "warn"))
    if c["id"] in ASKED:
        n = ASKED[c["id"]]
        terms.append(("Asked for", f"<a href={js(f'#why-{n}')}>{js(f'Request {n}, in the user words')}</a>", None, True))
    body = [definitions(terms)]
    for ref in c.get("code", []):
        body.append(code_block(repo, data, ref))
    if not verifiers:
        body.append(none("No verifier backs this claim."))
    for v in verifiers:
        state = v.get("state", "unknown")
        rung = tm.ladder(v)
        label = "{} check, {}{}, {} ({}):".format(v["kind"], TIER_WORD.get(v["tier"], v["tier"]), f", rung {rung}" if rung else "", state, v["id"])
        body.append(f"<p><strong>{js(label)}</strong>{js(' ' + reader(v['description'] + ' Provenance: ' + v['provenance']))}</p>")
        if "recorded" in v:
            body.append(f"<TerminalBlock title={js('Recorded: ' + v['recorded']['source'])} content={js(v['recorded']['result'])} />")
        if "formal" in v:
            link = v["formal"]["conformance"]
            body.append(f"<TerminalBlock title={js('Conformance link: ' + link['status'])} content={js(v['formal']['tool'] + ' ' + v['formal']['artifact'] + chr(10) + link['source'] + (chr(10) + link['detail'] if link.get('detail') else ''))} />")
        m = (v.get("mechanical") or {}).get("result")
        if m:
            body.append(f"<TerminalBlock title={js('Mechanical check at the PR head: ' + m['status'])} content={js('$ ' + m['command'] + chr(10) + m['detail'])} />")
        if "command" in v:
            b = v.get("baseline") or {}
            body.append(f"<CodeBlock language=\"bash\" filename={js('At the PR head: ' + b.get('status', 'not run'))} code={js('$ ' + ' '.join(v['command']['argv']))} />")
            if b.get("output_tail"):
                body.append(f"<TerminalBlock title={js('Output at the PR head')} content={js(b['output_tail'])} />")
        for k in controls.get(v["id"], []):
            r = k.get("result") or {}
            status = r.get("status", "not run")
            outcome = {"red": OUTCOME["caught"][0].lower(), "green": OUTCOME["missed"][0].lower()}.get(status, status)
            label = "The check {} ({}).".format(outcome, k["id"]) if status in ("red", "green") else "Control {}: {}.".format(k["id"], status)
            body.append(f"<p><strong>{js(label)}</strong>{js(' ' + reader(k['description']))}</p>")
            body += edit_blocks(k, data, repo)
            tail = r.get("output_tail", r.get("note", ""))
            if tail:
                body.append(f"<TerminalBlock title={js('Control ' + k['id'] + ' output')} content={js(tail)} />")
    summary = "{<>" + pill(c["verdict"]) + " " + inline(plain["what"], terms=False) + "</>}"
    return disclosure(summary, "\n".join(body), anchor=claim_anchor(c["id"]), meta=c["id"], jsx=True, share=True, lazy=True)


def edit_blocks(k: dict, data: dict, repo: str) -> list[str]:
    """The real before and after of a control: the patch of its scratch worktree (result.diff),
    else the same resolution in memory at the commit where the control runs."""
    commit = next((v.get("at") for v in data["verifiers"] if v["id"] == k["verifier"]), None) or data["head"]
    r = k.get("result") or {}
    if r.get("diff") and r.get("head") == commit:
        patches = coderef.split_patch(r["diff"])
    else:
        try:
            patches = coderef.control_patches(repo, commit, k["edits"])
        except coderef.AnchorError as exc:
            if any(e["op"] in coderef.ANCHOR_OPS for e in k["edits"]):
                fail(f"control {k['id']}: its anchor does not resolve at {commit[:10]}: {exc}")
            patches = None
    if patches is None:
        # A recorded formal control: its paths are relative to the formal copy, not to the repo.
        return [legacy_edit_block(e) for e in k["edits"]]
    out = []
    for path, patch in patches:
        if patch is None:
            out.append(f"<p><code>{js('changed bytes')}</code>{js(' ' + path)}</p>")
        else:
            out.append(f"<DiffBlock language={js(LANG.get(Path(path).suffix, 'text'))} filename={js(path)} patch={js(patch)} />")
    return out


def legacy_edit_block(edit: dict) -> str:
    lang = LANG.get(Path(edit["path"]).suffix, "text")
    name = js(edit["path"])
    if edit["op"] == "replace" and edit.get("find") != edit.get("replace"):
        return f"<DiffBlock language={js(lang)} filename={name} before={js(edit['find'])} after={js(edit['replace'])} />"
    if edit["op"] == "append" and edit.get("text"):
        return f"<DiffBlock language={js(lang)} filename={name} before={js('')} after={js(edit['text'])} />"
    detail = ", ".join(f"{k} {v}" for k, v in edit.items() if k not in ("op", "path"))
    return f"<p><code>{js(edit['op'])}</code>{js(' ' + edit['path'] + (': ' + detail if detail else ''))}</p>"


# ---- Level 5: verify the verifiers -----------------------------------------------------------

def mutation_label(text: str) -> str:
    """A short label for a planted bug, from its own description: the first clause."""
    head = re.split(r"(?<=[a-z0-9)])[:,.]\s", text.strip(), maxsplit=1)[0].rstrip(".")
    return head if len(head) <= 48 else head[:45].rsplit(" ", 1)[0] + "..."


def control_walkthrough(data: dict, spec: dict) -> dict:
    controls = {k["id"]: k for k in data["controls"]}
    verifiers = {v["id"]: v for v in data["verifiers"]}
    nodes, edges, steps, seen = [], [], [], set()
    for kid in spec["controls"]:
        if kid not in controls:
            fail(f"control walkthrough names {kid}, which the map does not have")
        k = controls[kid]
        v = verifiers[k["verifier"]]
        status = (k.get("result") or {}).get("status", "not run")
        outcome = "caught" if status == "red" else "cannot-fail" if v.get("state") == "cannot-fail" else "missed"
        word, tone, _ = OUTCOME[outcome]
        nodes.append({"id": f"plant-{kid}", "label": mutation_label(reader(k["description"])), "detail": f"control {kid}", "shape": "oval"})
        if v["id"] not in seen:
            seen.add(v["id"])
            argv = (v.get("command") or {}).get("argv", [])
            target = argv[-1] if argv and ("/" in argv[-1] or "." in argv[-1]) else "the whole project"
            nodes.append({"id": f"run-{v['id']}", "label": (v.get("independence") or {}).get("tool", v["kind"]), "detail": f"{target} ({v['id']})"})
        nodes.append({"id": f"out-{kid}", "label": word, "tone": tone, "detail": f"control {kid}"})
        edges += [{"id": f"{kid}-run", "from": f"plant-{kid}", "to": f"run-{v['id']}", "label": "plant, then run"},
                  {"id": f"{kid}-out", "from": f"run-{v['id']}", "to": f"out-{kid}", "label": word.lower()}]
        steps += [{"edgeId": f"{kid}-run", "caption": f"We plant a bug in a scratch copy. {reader(k['description'])} ({kid})"},
                  {"edgeId": f"{kid}-out", "caption": f"The check {word.lower()}. " + OUTCOME[outcome][2][0].upper() + OUTCOME[outcome][2][1:]}]
    return {"title": spec["title"], "description": spec["description"], "nodes": nodes, "edges": edges, "steps": steps}


def outcome_legend() -> str:
    items = [{"label": word, "tone": tone, "detail": meaning[0].upper() + meaning[1:]} for word, tone, meaning in OUTCOME.values()]
    return f"<Legend layout=\"list\" title={js('What a control shows')} items={js(items)} />"


def verifiers_level(data: dict, extra: dict) -> str:
    ran = [k for k in data["controls"] if k.get("result")]
    caught = [k for k in ran if k["result"].get("status") == "red"]
    parts = [para("A check earns trust only when it fails on a real bug. So we put one bug at a time into a scratch copy of the code, and we ran the check. These bugs are the controls."),
             outcome_legend(), para(f"{len(caught)} of {len(ran)} controls caught the bug. No model call ran, and the controls cost nothing.")]
    for i, spec in enumerate(extra.get("control_walkthroughs") or []):
        motion = control_walkthrough(data, spec)
        legend = [{"label": OUTCOME[o][0], "tone": OUTCOME[o][1]} for o in ("caught", "missed")] + [
            {"label": "planted bug", "glyph": "oval"}, {"label": "check", "glyph": "rect"}]
        parts.append(disclosure("Show the motion: " + spec["title"][0].lower() + spec["title"][1:], para(spec["description"]) + "\n" +
                                f"<DiagramWalkthrough layout=\"flow\" title={js(motion['title'])} description={js(motion['description'])} "
                                f"nodes={js(motion['nodes'])} edges={js(motion['edges'])} steps={js(motion['steps'])} legend={js(legend)} />",
                                anchor="verifiers-controls" + (str(i) if i else ""), lazy=True))
    parts.append(verifier_map(data))
    parts.append(next_link("unclaimed", "see the changed code that no claim covers"))
    return "\n".join(parts)


def verifier_map(data: dict) -> str:
    verdict_of = {c["id"]: c["verdict"] for c in data["claims"]}
    layer_of = {c["id"]: c.get("layer", "Claims") for c in data["claims"]}
    kinds: dict[str, dict] = {}
    links: dict[tuple[str, str], set[str]] = {}
    for v in data["verifiers"]:
        k = kinds.setdefault(v["kind"], {"n": 0, "guess": False, "recorded": 0, "checked": 0})
        k["n"] += 1
        k["guess"] |= v["tier"] == "guess"
        k["recorded"] += v.get("state") == "recorded"
        k["checked"] += v.get("state") == "checked"
        if v.get("state") in ("cannot-fail", "failing", "broken"):
            continue
        for cid in v["claims"]:
            links.setdefault((v["kind"], layer_of[cid]), set()).add(cid)
    layers = list(dict.fromkeys(layer_of.values()))
    layer_verdict = {layer: weakest(verdict_of[c] for c, lay in layer_of.items() if lay == layer) for layer in layers}
    kind_ids = {kind: f"k{i}" for i, kind in enumerate(kinds)}
    layer_ids = {layer: f"l{i}" for i, layer in enumerate(layers)}

    def tier(k: dict) -> str:
        if k["guess"]:
            return "a model judgment"
        if k["recorded"] == k["n"]:
            return "recorded, not run again"
        if k["checked"] == k["n"]:
            return "mechanical check"
        return "run again at the PR head"

    nodes = [{"id": kind_ids[kind], "label": f"{kind} ({k['n']})", "shape": KIND_GLYPH.get(kind, "rect"), "detail": tier(k),
              **({"stroke": "dashed"} if k["guess"] or k["recorded"] == k["n"] else {})} for kind, k in kinds.items()]
    covered = {layer for _, layer in links}
    nodes += [{"id": layer_ids[layer], "label": layer, "tone": TONE[layer_verdict[layer]], "detail": f"weakest: {layer_verdict[layer]}"} for layer in layers]
    edges = [{"from": kind_ids[kind], "to": layer_ids[layer], "label": f"{len(cids)} claims" if len(cids) > 1 else "1 claim"} for (kind, layer), cids in links.items()]
    if any(layer not in covered for layer in layers):
        nodes.append({"id": "none", "label": "no verifier", "shape": "oval", "stroke": "dashed", "tone": "err", "detail": "only the PR text, or nothing"})
        edges += [{"from": "none", "to": layer_ids[layer], "label": "no check"} for layer in layers if layer not in covered]
    used = [v for v in VERDICTS if v in set(layer_verdict.values())]
    glyphs = sorted({KIND_GLYPH.get(k, "rect") for k in kinds}, key=list(GLYPH_FAMILY).index)
    legend = ([{"label": v, "tone": TONE[v]} for v in used] + [{"label": GLYPH_FAMILY[g], "glyph": g} for g in glyphs]
              + [{"label": "run again at the PR head", "stroke": "solid"}, {"label": "a model judgment, or recorded only", "stroke": "dashed"}])
    vcontrols: dict[str, list[str]] = {}
    for k in data["controls"]:
        status = (k.get("result") or {}).get("status", "not run")
        vcontrols.setdefault(k["verifier"], []).append(f"{k['id']} {mutation_label(reader(k['description']))}: {dict(red='caught the bug', green='missed the bug').get(status, status)}")
    vflags: dict[str, list[dict]] = {}
    for f in data["flags"]:
        vflags.setdefault(f["subject"], []).append({"label": f["flag"], "tone": FLAG_TONE.get(f["flag"], "warn")})
    columns = [{"key": "id", "label": "Verifier", "kind": "id", "width": "5.5rem"},
               {"key": "kind", "label": "Kind", "kind": "tags", "width": "9.5rem"},
               {"key": "state", "label": "State", "kind": "status", "width": "8.5rem"},
               {"key": "claims", "label": "Claims", "kind": "tags", "width": "9rem"},
               {"key": "controls", "label": "Controls"}]
    rows = [{"id": f"verifier-{slug(v['id'])}", "cells": {
        "id": {"text": v["id"], **({"badges": vflags[v["id"]]} if v["id"] in vflags else {})},
        "kind": {"badges": [{"label": v["kind"], "glyph": KIND_GLYPH.get(v["kind"], "rect"), "stroke": "dashed" if v["tier"] == "guess" else "solid"}]},
        "state": {"text": v.get("state", "unknown"), "status": STATE_TONE.get(v.get("state", ""), "neutral")},
        "claims": {"badges": [{"label": cid, "tone": TONE.get(verdict_of.get(cid, ""), "neutral")} for cid in v["claims"]]},
        "controls": "; ".join(vcontrols.get(v["id"], [])) or None}} for v in data["verifiers"]]
    figure = (para("Each kind of check, with an arrow to each group of claims that it backs. A group takes the colour and the word of its weakest claim. A group with no check is a Gap, and the box marked no verifier points to it.")
              + f"\n<DiagramCanvas layout=\"flow\" title={js('From checks to claims')} description={js('Each kind of check and the claim groups it backs, with every claim group shown.')} "
              f"nodes={js(nodes)} edges={js(edges)} legend={js(legend)} />")
    return (disclosure("Show the map from checks to claims", figure, anchor="verifiers-map", lazy=True) + "\n"
            + disclosure(f"Show all {len(data['verifiers'])} verifiers", table(columns, rows, "Verifiers"), anchor="verifiers-table",
                         lazy=True, contains=[r["id"] for r in rows]))


# ---- Level 6: unclaimed changes --------------------------------------------------------------

def unclaimed(data: dict, extra: dict, diff: Diff) -> str:
    spec = extra.get("unclaimed") or {}
    notes = spec.get("notes") or {}
    for path in notes:
        if path not in diff.files:
            fail(f"unclaimed.notes names {path}, which the diff does not change")
    cited: dict[str, set[int] | None] = {}
    for c in data["claims"]:
        for ref in c.get("code", []):
            if coderef.is_anchor(ref) or "start" in ref:
                r = RESOLVED.get(coderef.ref_key(ref)) or coderef.resolve(diff.repo, data["head"], ref, cap=False)
                span = set(range(r.start, r.end + 1))
            else:
                span = None
            if ref["path"] in cited and cited[ref["path"]] is None:
                continue
            cited[ref["path"]] = None if span is None else (cited.get(ref["path"]) or set()) | span
    rows = []
    for path, (added, removed) in diff.files.items():
        if not is_code(path) or path in diff.deleted or not added:
            continue
        new = diff.added_lines.get(path, set())
        if path not in cited:
            share, note = 0, "none"
        else:
            span = cited[path]
            covered = len(new) if span is None else len(new & span)
            if added < 100 or covered >= 0.1 * max(len(new), 1):
                continue
            share, note = covered, f"{covered} of {len(new)} new lines"
        rows.append((path in notes, len(new) - share, path, added, removed, note))
    core = spec.get("core") or []
    is_core = lambda path: any(path.startswith(x.rstrip("/") + "/") or path == x for x in core)  # noqa: E731
    # Risk first: a core file, then the most new lines that no claim covers.
    rows.sort(key=lambda r: (not is_core(r[2]), -r[1], r[2]))
    columns = [{"key": "file", "label": "File", "kind": "id", "width": "21rem"},
               {"key": "change", "label": "+/−", "kind": "number", "width": "8rem"},
               {"key": "reason", "label": "Why it matters"}]

    def row(r) -> dict:
        _, _, path, added, removed, note = r
        cited = "No claim cites it." if note == "none" else f"Claims cite {note}."
        reason = ("Core harness file. " if is_core(path) else "") + (notes.get(path) or cited)
        return {"cells": {"file": {"text": diff.short(path)}, "change": f"{lines(added, '+')} / {lines(removed, '−')}",
                          "reason": reason}}

    intro = spec.get("intro") or "These source files change in the PR, but no claim cites them, or a claim cites only a small part of a large new file. No check in this map covers them. Read them yourself, or ask the author for a claim and a test."
    parts = [para(intro)]
    if not rows:
        parts.append(none("Each changed source file has a claim. Nothing is left over."))
    else:
        parts.append(compact_table(columns, [row(r) for r in rows[:VISIBLE_UNCLAIMED]], "Changed code that no claim covers, riskiest first"))
        if len(rows) > VISIBLE_UNCLAIMED:
            more = rows[VISIBLE_UNCLAIMED:]
            parts.append(disclosure(f"Show {len(more)} more files", compact_table(columns, [row(r) for r in more], "More changed code that no claim covers"), lazy=True))
    parts.append(para("Tests, documents and data files are not in this list."))
    return "\n".join(parts)


# ---- Levels 7 and 8 --------------------------------------------------------------------------

def bullets(items: list[str], empty: str) -> str:
    if not items:
        return none(empty)
    return "<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>"


def tradeoffs(extra: dict) -> str:
    return "\n".join([
        subsection("tradeoffs-list", js("Trade-offs"), bullets(extra.get("tradeoffs", []), "No trade-offs recorded.")),
        subsection("tradeoffs-concerns", js("Concerns"), bullets(extra.get("concerns", []), "No concerns recorded.")),
        subsection("tradeoffs-verifications", js("How we checked this explainer"), bullets(extra.get("verifications", []), "No verifications recorded."))])


def exercises() -> str:
    return none("This chapter is a placeholder. The learning app fills it.")


def glossary_level(glossary_used: list[tuple[str, str]]) -> str:
    """Every term that the page uses, from the one glossary source that the tooltips also read."""
    if not glossary_used:
        return none("The page uses no term that needs a definition.")
    intro = para("Each word below has one meaning on this page. In the text, a word with a dotted line shows its meaning when you point to it, focus it or tap it.")
    return intro + "\n" + f"<div id={js('glossary')}>" + definitions(((t, m, None) for t, m in glossary_used)) + "</div>"


# ---- Glossary --------------------------------------------------------------------------------

def norm(word: str) -> str:
    w = word.lower()
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def prose(data: dict, extra: dict) -> list[str]:
    """The plain-language text of the page, without code: what the glossary must cover."""
    out = []
    s = extra.get("story") or {}
    out += [s.get(k, "") for k in ("summary", "problem", "change", "trust")]
    loop_ = extra.get("loop") or {}
    out.append(loop_.get("intro", ""))
    out += [st["text"] for st in loop_.get("steps", [])]
    motion = loop_.get("walkthrough") or {}
    out += [n.get("label", "") for n in motion.get("nodes", [])] + [st.get("caption", "") for st in motion.get("steps", [])]
    for spec in (extra.get("diagrams") or {}).values():
        out += [spec.get("title", ""), spec.get("description", "")]
        out += [n.get("label", "") + ". " + n.get("detail", "") for n in (spec.get("eli5") or {}).get("nodes", [])]
        out += [e.get("label", "") for e in (spec.get("eli5") or {}).get("edges", [])]
    ch = extra.get("change") or {}
    out += [ch.get("intro", "")] + [a["name"] for a in ch.get("areas", [])] + [a.get("note", "") for a in ch.get("areas", [])]
    out += list(((extra.get("unclaimed") or {}).get("notes") or {}).values())
    for p in data["promises"]:
        out += [p["label"], p["sentence"], p.get("reviewer_action", "")]
    for c in data["claims"]:
        out += list((c.get("plain") or {}).values())
    for r in extra.get("risks") or []:
        out += [r.get("why", ""), r.get("fix", "")]
    out += extra.get("tradeoffs", []) + extra.get("concerns", []) + extra.get("verifications", [])
    return [re.sub(r"`[^`]*`", " ", t) for t in out if t]


def required_terms(texts: list[str], ids: set[str]) -> set[str]:
    """Acronyms, and capitalised words inside a sentence: each needs a definition."""
    found = set()
    for text in texts:
        for m in re.finditer(r"(?<![\w$#.-])([0-9]*[A-Z][A-Z0-9]*(?:-[0-9A-Z]+)*)(?![\w-])", text):
            tok = m.group(1)
            if len(tok) >= 2 and re.search(r"[A-Z]", tok) and tok not in ids and tok not in STOP_ACRONYMS and not re.fullmatch(r"[CVKG]\d+[a-z]?", tok):
                found.add(tok)
        for m in re.finditer(r"(?<=[a-z0-9,;)] )([A-Z][a-z]+)\b", text):
            if not code_like(m.group(1)):
                found.add(m.group(1))
    return found


def build_glossary(data: dict, extra: dict) -> list[tuple[str, str]]:
    entries = [(g["term"], g["meaning"], g.get("aliases", [])) for g in data.get("glossary") or []]
    have = {norm(t) for t, _, _ in entries}
    entries += [e for e in BUILTIN_GLOSSARY if norm(e[0]) not in have]
    texts = prose(data, extra)
    blob = " " + " ".join(texts).lower() + " "
    ids = {x["id"] for x in data["claims"] + data["verifiers"] + data["controls"] + data["promises"]}
    defined = {norm(form) for term, _, aliases in entries for form in [term, *aliases]}
    missing = sorted(t for t in required_terms(texts, ids) if norm(t) not in defined)
    if missing:
        fail("the page uses terms that the glossary does not define: " + ", ".join(missing)
             + ". Add each to `glossary` in the trust map (commands/map.md).")

    def used(form: str) -> bool:
        f = re.escape(form.lower())
        return re.search(rf"(?<![\w-]){f}(?:s|es)?(?![\w-])", blob) is not None

    return sorted(((t, m) for t, m, aliases in entries if any(used(f) for f in [t, *aliases])), key=lambda e: e[0].lower())


# ---- Checks on the generated levels ----------------------------------------------------------

def strip_collapsed(text: str) -> str:
    """Remove the body of each Disclosure (its summary stays) and each DataTable."""
    text = re.sub(r"<DataTable [^\n]*?/>", "", text)
    text = re.sub(r"<Legend [^\n]*?/>", "", text)
    out, i = [], 0
    while True:
        start = text.find("<Disclosure", i)
        if start < 0:
            out.append(text[i:])
            return "".join(out)
        tag_end = text.index(">", start) + 1
        out.append(text[i:tag_end])
        depth, j = 1, tag_end
        while depth:
            nxt_open = text.find("<Disclosure", j)
            nxt_close = text.find("</Disclosure>", j)
            if nxt_open != -1 and nxt_open < nxt_close:
                depth, j = depth + 1, nxt_open + 1
            else:
                depth, j = depth - 1, nxt_close + len("</Disclosure>")
        out.append("</Disclosure>")
        i = j


def visible_strings(text: str):
    """(attribute or key, string) for each string in each JSX expression, skipping layout data and
    the Detailed mode of a diagram."""
    decoder = json.JSONDecoder()
    i = 0
    while True:
        i = text.find("{", i)
        if i < 0:
            return
        try:
            value, end = decoder.raw_decode(text, i + 1)
        except json.JSONDecodeError:
            i += 1
            continue
        if end >= len(text) or text[end] != "}":
            i += 1
            continue
        attr = re.search(r"(\w+)=$", text[:i])
        name = attr.group(1) if attr else "text"
        if name not in SKIP_ATTRS:
            yield from walk(value, name)
        i = end + 1


def walk(value, key: str):
    if isinstance(value, str):
        if key not in ROW_OF_SKIP_KEYS:
            yield key, value
    elif isinstance(value, list):
        for item in value:
            yield from walk(item, key)
    elif isinstance(value, dict):
        for k, item in value.items():
            yield from walk(item, k)


def leak_errors(level: str, mdx: str, ids: set[str], ids_only: bool = False) -> list[str]:
    """IDs and code names that a reader sees without opening anything. With ids_only (the prose
    levels 4, 5 and 7) only IDs and the words "fact tier" count: code may show there."""
    shown = strip_collapsed(mdx)
    errors = []
    if not ids_only:
        for tag in ("<code>", "<CodeBlock", "<DiffBlock", "<TerminalBlock"):
            if tag in shown:
                errors.append(f"{level}: {tag} outside a collapsed block")
    id_re = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, sorted(ids, key=len, reverse=True))) + r")(?![\w-])") if ids else None
    for key, text in visible_strings(shown):
        if id_re and id_re.search(text):
            errors.append(f"{level}: the ID {id_re.search(text).group(1)} is visible in {key}: {text[:80]!r}")
        if re.search(r"\bfact tier\b", text, re.I):
            errors.append(f"{level}: the words 'fact tier' are visible in {key}: {text[:80]!r}")
        hit = None if ids_only else code_like(text)
        if hit:
            errors.append(f"{level}: {hit} is visible in {key}: {text[:80]!r}")
    return errors


def link_errors(texts: dict[str, str], extra_ids: set[str], data: dict) -> list[str]:
    blob = "\n".join(texts.values())
    defined = set(re.findall(r'\bid=\{"([^"]+)"\}', blob)) | set(re.findall(r'"id":\s*"([^"]+)"', blob)) | extra_ids
    errors = [f"the link #{h} has no target" for h in sorted(set(re.findall(r'"href":\s*"#([^"]+)"', blob)) | set(re.findall(r'href=\{"#([^"]+)"\}', blob)) | set(re.findall(r'href="#([^"]+)"', blob))) if h not in defined]
    for c in data["claims"]:
        n = len(re.findall(r'\bid=\{"' + re.escape(claim_anchor(c["id"])) + r'"\}', blob))
        if n != 1:
            errors.append(f"claim {c['id']} has {n} claim blocks; it needs exactly one, so a reader can reach it")
    return errors


# ---- PR-body section -------------------------------------------------------------------------

def mermaid(data: dict) -> str:
    layers: dict[str, dict[str, int]] = {}
    for c in data["claims"]:
        layers.setdefault(c.get("layer", "Claims"), {v: 0 for v in VERDICTS})[c["verdict"]] += 1
    out = ["```mermaid", "flowchart LR"]
    for i, (layer, counts) in enumerate(layers.items()):
        out.append(f'  L{i}["{layer}"]')
        out += [f"  L{i} -->|{counts[v]}| {v}" for v in VERDICTS if counts[v]]
    out += [f'  {v}(["{v}"])' for v in VERDICTS]
    out += ["  classDef proven fill:#d7f0dd,stroke:#2f7d46", "  classDef gap fill:#fbe0dc,stroke:#b3402f",
            "  class Proven proven", "  class Gap gap", "```"]
    return "\n".join(out)


def ready_lines(ready: dict) -> list[str]:
    """The ready checklist, from ready.py: one line per gate."""
    out = ["### Ready checklist", ""]
    for g in ready["gates"]:
        out.append(f"- [{'x' if g['pass'] else ' '}] **Gate {g['n']}, {g['name']}:** {'pass' if g['pass'] else 'fail'}. {g['detail']}")
    return out


def merge_line(data: dict, ready: dict | None, explainer_url: str | None) -> str:
    """The merge verdict for the PR body: the same answer as the page, each item a link to its promise."""
    form, items = merge_verdict(data, ready)
    word = MERGE_WORDS[form][0]
    if not items:
        return f"**Merge verdict: {word}.** {MERGE_WORDS[form][2]}"
    link = (lambda i: f"[{i['label']}]({explainer_url}{i['href']})") if explainer_url else (lambda i: f"**{i['label']}**")  # noqa: E731
    shown = items[:MAX_MERGE_ITEMS]
    lines_ = [f"**Merge verdict: {word}.** {MERGE_WORDS[form][2][0].upper() + MERGE_WORDS[form][2][1:]}", ""]
    lines_ += [f"{n}. {link(i)}. {reader(i['text'])}" for n, i in enumerate(shown, 1)]
    rest = items[MAX_MERGE_ITEMS:]
    if rest:
        lines_ += ["", f"And {len(rest)} more: " + ", ".join(link(i) for i in rest) + "."]
    return "\n".join(lines_)


def claim_link(c: dict, data: dict, repo: str | None) -> str:
    """The claim ID, linked to the permalink of its first code ref. The link comes from the git
    remote and the resolved lines, never from typed text."""
    refs = c.get("code") or []
    if not repo or not refs:
        return c["id"]
    r = RESOLVED.get(coderef.ref_key(refs[0]))
    if r is None:
        try:
            r = coderef.resolve(repo, data["head"], refs[0])
        except coderef.AnchorError as exc:
            fail(f"claim {c['id']}: a code ref does not resolve at the head: {exc}")
    link = coderef.permalink(repo, data["head"], r.path, r.start, r.end, data.get("repo"))
    return f"[{c['id']}]({link})" if link else c["id"]


def pr_section(data: dict, extra: dict, explainer_url: str | None, ready: dict | None = None, repo: str | None = None) -> str:
    s = data["summary"]
    out = ["## Trust map", "", merge_line(data, ready, explainer_url), ""]
    if ready:
        out += ready_lines(ready) + [""]
    out += [mermaid(data), "", "| Claim | Verdict | Tier | Why |", "|---|---|---|---|"]
    esc = lambda t: t.replace("|", chr(92) + "|")  # noqa: E731
    for c in data["claims"]:
        verdict = f"**{c['verdict']}**" + (f" (waived: {esc(c['waiver']['reason'])})" if c.get("waiver") else "")
        out.append(f"| {claim_link(c, data, repo)}: {esc(c['text'])} | {verdict} | {c.get('tier') or '-'} | {esc(c['reason'])} |")
    out.append("")
    out.append("- **Verdicts:** " + ", ".join(f"{s.get(v, 0)} {v}" for v in VERDICTS) + ".")
    claims = {c["id"]: c for c in data["claims"]}
    out.append("- **Promises:** " + " ".join(f"{p['label']}: {strength}, {strongest_tier(claims[c] for c in cids)[0].lower()}{strongest_tier(claims[c] for c in cids)[1:]}" for p, strength, cids in promises_in_order(data)))
    waived = [c for c in data["claims"] if c.get("waiver")]
    if waived:
        out.append("- **Waived:** " + " ".join(f"{c['id']}: {c['waiver']['reason']}" for c in waived))
    loud = [f for f in data["flags"] if f.get("loud")]
    dead = [f["detail"] for f in loud if f["flag"] == "cannot-fail"]
    out.append("- **Cannot fail:** " + (" ".join(dead) if dead else "none."))
    out += [f"- **{f['flag']}:** {f['detail']}" for f in loud if f["flag"] != "cannot-fail"]
    ran = [k for k in data["controls"] if k.get("result")]
    out.append(f"- **Controls:** {len(ran)} ran in scratch worktrees. Cost: $0, with no model call.")
    out += [f"- {b}" for b in extra.get("bullets", [])]
    if explainer_url:
        out.append(f"- **Explainer:** {explainer_url}")
    return "\n".join(out) + "\n"


# ---- Main ------------------------------------------------------------------------------------

CHAPTERS = ["story", "loop", "change", "promises", "verifiers", "unclaimed", "tradeoffs", "exercises", "glossary"]
CHAPTER_COMPONENTS = ("ChipLinks, CodeBlock, DataTable, Definition, DefinitionList, DiagramCanvas, DiagramModes, "
                      "DiagramWalkthrough, DiffBlock, Disclosure, Legend, StatusPill, Step, Steps, Subsection, Term, TerminalBlock")


def chapter_file(repo_path: str, name: str, body: str) -> str:
    """One self-contained MDX unit: its own imports and its content, so an app can embed it."""
    return (f"{{/* understando level: {name}. scripts/explain.py writes it from trust-map.json and explain.json. */}}\n"
            f"import {{ {CHAPTER_COMPONENTS} }} from '{repo_path}/visual-explainer-mdx/components';\n\n{body}\n")


def anchors(items: list[tuple[str, str]]) -> str:
    return js([{"id": i, "label": label} for i, label in items])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--extra")
    ap.add_argument("--runtime")
    ap.add_argument("--explainer-url")
    ap.add_argument("--journal", help="journal.jsonl of the run: adds the 'Why it was built this way' level")
    ap.add_argument("--ready", help="ready.json of the run: puts the ready checklist at the top")
    args = ap.parse_args()
    data = tm.load(args.map)
    errors = tm.validate(data)
    if errors:
        fail("the map is invalid:\n" + "\n".join(errors))
    if "summary" not in data:
        fail("run scripts/verdicts.py first; the map has no verdicts")
    for v in data["verifiers"]:
        if "mechanical" in v:
            got = mechanical.run(args.repo, data["base"], data["head"], v["mechanical"])
            old = v["mechanical"].get("result") or {}
            if (old.get("status"), old.get("detail")) != (got["status"], got["detail"]):
                fail(f"{v['id']}: the mechanical check now gives {got['status']} ({got['detail'].splitlines()[0]}); "
                     f"the map records {old.get('status')}. Run scripts/mechanical.py, then verdicts.py.")
    extra = tm.load(args.extra) if args.extra else {}
    template = tm.ROOT / "templates" / "three-level.mdx"
    pasted = coderef.pasted(args.repo, data["head"], coderef.guard_inputs(data, extra, [template]))
    if pasted:
        fail("the input holds code that a person or a model typed. Code comes in through a ref:\n  " + "\n  ".join(pasted))
    out = Path(args.out)
    (out / "chapters").mkdir(parents=True, exist_ok=True)
    for old in (out / "chapters").glob("*.mdx"):
        old.unlink()
    runtime = runtime_path(args.runtime)
    diff = Diff(args.repo, data["base"], data["head"])
    used_terms = build_glossary(data, extra)
    TERMS.load(used_terms, {g["term"]: g.get("aliases", []) for g in data.get("glossary") or []})
    ready = tm.load(args.ready) if args.ready and Path(args.ready).is_file() else None
    if ready and ready.get("head") != data["head"]:
        ready = None
    journal = load_journal(args.journal)
    # Each level in page order, so a term shows its tooltip at its first use in each level and an
    # abbreviation is spelled out once, at its first use on the page.
    builders = [("story", lambda: story(data, extra, used_terms, ready, "why" if has_why else "loop")),
                ("why", lambda: why_level(data, journal)),
                ("loop", lambda: loop(data, extra, args.repo)), ("change", lambda: change(data, extra, diff)),
                ("promises", lambda: promises(data, extra, args.repo)), ("verifiers", lambda: verifiers_level(data, extra)),
                ("unclaimed", lambda: unclaimed(data, extra, diff)), ("tradeoffs", lambda: tradeoffs(extra)),
                ("exercises", exercises), ("glossary", lambda: glossary_level(used_terms))]
    has_why = bool([r for r in journal if r.get("kind") == "prompt"] or [i for i in data.get("invariants", []) if i["status"] in ("accepted", "proposed")])
    bodies = {}
    for name, build in builders:
        TERMS.level()
        # The why level keeps its own words: its prose has its own STE check (tests/mode-e2e.sh).
        TERMS.enabled = name != "why"
        bodies[name] = build()
    TERMS.enabled = True
    why = bodies.pop("why")
    ids = {x["id"] for x in data["claims"] + data["verifiers"] + data["controls"]}
    problems = [e for name in ("story", "loop", "change") for e in leak_errors(name, bodies[name], ids)]
    problems += [e for name in ("promises", "verifiers", "tradeoffs") for e in leak_errors(name, bodies[name], ids, ids_only=True)]
    if why:
        # The user's quotes are their own words; the generated prose around them follows the rule.
        problems += leak_errors("why", re.sub(r'<blockquote data-quote="user">.*?</blockquote>', "", why, flags=re.S), ids, ids_only=True)
    chapters = [(f"{i:02d}-{name}", name) for i, name in enumerate(CHAPTERS, 1)]
    if why:
        bodies["why"] = why
        chapters.insert(1, ("01a-why", "why"))
    problems += link_errors(bodies, set(CHAPTERS) | {"why"}, data)
    if problems:
        fail("the levels break the ladder rules:\n  " + "\n  ".join(problems))
    (out / "pr-section.md").write_text(pr_section(data, extra, args.explainer_url, ready, args.repo), encoding="utf-8")
    coderef.write_cache(out, data["head"], RESOLVED)
    for stem, name in chapters:
        (out / "chapters" / f"{stem}.mdx").write_text(chapter_file(runtime, name, bodies[name]), encoding="utf-8")
    order = promises_in_order(data)
    nav = {
        "STORY_ANCHORS": [("story-verdict", "Can you merge it?")] + [("story-ready", "Ready checklist")] * bool(ready) + [("story-promises", "What the PR promises")],
        "CHANGE_ANCHORS": [("change-diagram", "Before and after"), ("change-table", "Deleted and replaced")]
                          + [("change-" + slug(n), diagram(extra, n)["title"]) for n in (extra.get("change") or {}).get("diagrams") or []],
        "PROMISE_ANCHORS": [(promise_anchor(p["id"]), p["label"]) for p, _, _ in order],
        "VERIFIER_ANCHORS": [("verifiers-controls", "Plant a bug")] * bool(extra.get("control_walkthroughs")) + [("verifiers-map", "Checks to claims"), ("verifiers-table", "All verifiers")],
        "TRADEOFFS_ANCHORS": [("tradeoffs-list", "Trade-offs"), ("tradeoffs-concerns", "Concerns"), ("tradeoffs-verifications", "How we checked")],
    }
    title = f"PR #{data.get('pr')}: " + (data.get("title") or data["repo"])
    summary = (extra.get("story") or {}).get("summary") or "What this PR changes, and how far to trust it."
    filled = template.read_text(encoding="utf-8")
    filled = filled.replace("{{REPO}}", runtime).replace("{{TITLE}}", json.dumps(title)).replace("{{SUMMARY}}", json.dumps(summary))
    for key, items in nav.items():
        filled = filled.replace("{{" + key + "}}", anchors(items))
    filled = filled.replace("{{WHY_IMPORT}}\n", "import Why from './chapters/01a-why.mdx';\n" if why else "")
    filled = filled.replace("{{WHY_SECTION}}\n", ('<Section id="why" title="Why it was built this way" navLabel="Why it was built this way">\n<Why />\n</Section>\n\n') if why else "")
    (out / "explainer.mdx").write_text(filled, encoding="utf-8")
    print(f"wrote {out / 'pr-section.md'}")
    print(f"wrote {out / 'explainer.mdx'} and {len(chapters)} levels in {out / 'chapters'}")
    print(f"glossary: {len(used_terms)} terms; promises: " + ", ".join(f"{p['id']} {s}" for p, s, _ in order))
    return 0


if __name__ == "__main__":
    sys.exit(main())
