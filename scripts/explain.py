#!/usr/bin/env python3
"""Build the PR-body section and the three-level explainer source from a trust map.

    python3 scripts/explain.py --map trust-map.json --repo <git repo> --out DIR \
        [--extra explain.json] [--runtime REPO] [--explainer-url URL]

Writes:
  DIR/pr-section.md        the short PR-body section: one diagram, the claims-and-verdicts table,
                           and short bullets
  DIR/explainer.mdx        the explainer entry (templates/three-level.mdx, filled): the shell, the
                           chapter rail, and one Section for each chapter file
  DIR/chapters/NN-*.mdx    one self-contained MDX unit for each chapter: orientation, guided tour,
                           confidence, evidence, trade-offs, exercises (a placeholder)

--runtime is the Artifacture checkout. $UNDERSTANDO_VE_RUNTIME sets it too. The default asks the
visual-explainer CLI:
`node ~/.claude/skills/visual-explainer/scripts/artifacture.mjs path`.
Export the HTML after this script with the visual-explainer CLI (see commands/explain.md).

explain.json (optional, written by the agent) holds what the trust map does not:
  {"orientation": [str],                      about five STE sentences: what the PR does and why
   "architecture": {"description", "nodes", "edges"},
   "tour": [{"id", "title", "text": [str], "code": [codeRef], "claims": [claim id],
             "diagram"?: name, "walkthrough"?: name}],   in execution order; each claim once or more
   "diagrams": {name: {"title", "description", "nodes", "edges"}},           static
   "walkthroughs": {name: {"title", "description", "nodes", "edges", "steps"}},   animated
   "control_walkthroughs": [{"title", "description", "controls": [control id]}],
   "risks": [{"claims": [claim id], "why": str, "fix": str}],   the weakest high-stakes claims first
   "tradeoffs": [str], "concerns": [str], "verifications": [str], "bullets": [str]}
Nodes and edges use the DiagramCanvas shape: {id, label} and {from, to, label?}. A node label that
names claim IDs (C05, or C11-C14) takes the colour and the word of the weakest of their verdicts.
Without a tour, the tour has one stop per claim layer. Without risks, it lists the Gap and
Asserted claims.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tm  # noqa: E402

VERDICTS = ["Proven", "Backed", "Asserted", "Gap"]
MAX_SNIPPET = 30
LANG = {".py": "python", ".ts": "ts", ".tsx": "tsx", ".js": "js", ".mjs": "js", ".json": "json",
        ".md": "markdown", ".sh": "bash", ".toml": "toml", ".yml": "yaml", ".yaml": "yaml"}


def js(value) -> str:
    """A JSX expression that holds `value` as data, so MDX never parses it as markup.

    Escape < and > as \\u003c and \\u003e. JSON syntax holds them only inside strings, so the
    value does not change, and the MDX preflight never reads code text as a component tag. The
    preflight decodes the escapes before it highlights code, and the highlighter escapes its output."""
    text = json.dumps(value, ensure_ascii=False)
    return "{" + text.replace("<", "\\u003c").replace(">", "\\u003e") + "}"


def snippet(repo: str, head: str, ref: dict) -> tuple[str, int] | None:
    out = subprocess.run(["git", "-C", repo, "show", f"{head}:{ref['path']}"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    lines = out.stdout.splitlines()
    start = ref.get("start", 1)
    end = min(ref.get("end", start + MAX_SNIPPET - 1), start + MAX_SNIPPET - 1, len(lines))
    return "\n".join(lines[start - 1:end]), start


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


def mermaid(data: dict) -> str:
    layers: dict[str, dict[str, int]] = {}
    for c in data["claims"]:
        layer = c.get("layer", "Claims")
        layers.setdefault(layer, {v: 0 for v in VERDICTS})[c["verdict"]] += 1
    lines = ["```mermaid", "flowchart LR"]
    for i, (layer, counts) in enumerate(layers.items()):
        lines.append(f'  L{i}["{layer}"]')
        for v in VERDICTS:
            if counts[v]:
                lines.append(f"  L{i} -->|{counts[v]}| {v}")
    for v in VERDICTS:
        lines.append(f'  {v}(["{v}"])')
    lines += ["  classDef proven fill:#d7f0dd,stroke:#2f7d46", "  classDef gap fill:#fbe0dc,stroke:#b3402f",
              "  class Proven proven", "  class Gap gap", "```"]
    return "\n".join(lines)


def pr_section(data: dict, extra: dict, explainer_url: str | None) -> str:
    s = data["summary"]
    out = ["## Trust map", "", mermaid(data), "",
           "| Claim | Verdict | Why |", "|---|---|---|"]
    for c in data["claims"]:
        text = c["text"].replace("|", "\\|")
        out.append(f"| {c['id']}: {text} | **{c['verdict']}** | {c['reason'].replace('|', chr(92) + '|')} |")
    out.append("")
    out.append(f"- **Verdicts:** {s['Proven']} Proven, {s['Backed']} Backed, {s['Asserted']} Asserted, {s['Gap']} Gap.")
    loud = [f for f in data["flags"] if f.get("loud")]
    dead = [f["detail"] for f in loud if f["flag"] == "cannot-fail"]
    out.append("- **Cannot fail:** " + (" ".join(dead) if dead else "none."))
    for f in loud:
        if f["flag"] != "cannot-fail":
            out.append(f"- **{f['flag']}:** {f['detail']}")
    ran = [k for k in data["controls"] if k.get("result")]
    out.append(f"- **Controls:** {len(ran)} ran in scratch worktrees. Cost: $0, with no model call.")
    out += [f"- {b}" for b in extra.get("bullets", [])]
    if explainer_url:
        out.append(f"- **Explainer:** {explainer_url}")
    return "\n".join(out) + "\n"


# One colour key for the whole explainer. The tones are visual-explainer's --ve-status-* ramp.
TONE = {"Proven": "ok", "Backed": "info", "Asserted": "warn", "Gap": "err"}
STATE_TONE = {"proven": "ok", "recorded": "info", "cannot-fail": "err"}
FLAG_TONE = {"cannot-fail": "err", "control-missed": "warn", "same-family": "warn"}
# Verifier kind is a glyph, so it never competes with the verdict colours. Guess tier is dashed and hatched.
KIND_GLYPH = {"type-pin": "rect", "boundary": "rect", "parity": "rect", "golden": "rect",
              "contract-format": "rect", "integration": "oval", "unit": "oval", "e2e": "oval",
              "eval": "oval", "measurement": "oval", "model": "diamond"}
GLYPH_FAMILY = {"rect": "static check", "oval": "run check", "diamond": "model judge"}
VERDICT_LEGEND = [{"label": v, "tone": TONE[v]} for v in VERDICTS]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def claim_anchor(cid: str) -> str:
    return f"claim-{slug(cid)}"






def glyph(kind: str) -> str:
    return KIND_GLYPH.get(kind, "rect")


def inline(text: str) -> str:
    """JSX for STE text. A `backtick` span becomes code; everything else stays a string expression."""
    parts = text.split("`")
    out = []
    for i, part in enumerate(parts):
        if not part:
            continue
        out.append(f"<code>{js(part)}</code>" if i % 2 else js(part))
    return "".join(out)


def definitions(items) -> str:
    """A DefinitionList of (term, STE text, tone or None)."""
    body = "".join(f"<Definition term={js(term)}" + (f" tone=\"{tone}\"" if tone else "") + f">{inline(text)}</Definition>"
                   for term, text, tone in items)
    return f"<DefinitionList>{body}</DefinitionList>"


def subsection(anchor: str | None, title: str, body: str, level: int = 3, marker: str | None = None) -> str:
    """A Subsection: a titled block under a rule. `title` is a JSX expression; an anchor makes it a rail target."""
    attrs = (f" id={js(anchor)}" if anchor else "") + (f" level={{{level}}}" if level != 3 else "") + (f" marker={js(marker)}" if marker else "")
    return f"<Subsection{attrs} title={title}>\n{body}\n</Subsection>"


def none(text: str) -> str:
    return f"<p><em>{js(text)}</em></p>"


def table(columns: list[dict], rows: list[dict], label: str) -> str:
    return f"<DataTable label={js(label)} columns={js(columns)} rows={js(rows)} />"




def flags_by_claim(data: dict) -> dict[str, list[dict]]:
    backs = {v["id"]: v["claims"] for v in data["verifiers"]}
    out: dict[str, list[dict]] = {}
    for f in data["flags"]:
        for cid in backs.get(f["subject"], []):
            badge = {"label": f"{f['flag']} {f['subject']}", "tone": FLAG_TONE.get(f["flag"], "warn")}
            if badge not in out.setdefault(cid, []):
                out[cid].append(badge)
    return out


def by_verdict(data: dict) -> list[tuple[str, list[dict]]]:
    return [(v, [c for c in data["claims"] if c["verdict"] == v]) for v in VERDICTS
            if any(c["verdict"] == v for c in data["claims"])]


def intro(data: dict, verdict: str) -> str:
    text = (data.get("verdict_intros") or {}).get(verdict)
    return f"<p>{inline(text)}</p>" if text else ""


def glossary(data: dict) -> str:
    items = data.get("glossary") or []
    if not items:
        return f"<p>{js('This trust map has no glossary.')}</p>"
    return definitions((g["term"], g["meaning"], None) for g in items)


def weakest(cids: list[str], verdict_of: dict[str, str]) -> str | None:
    found = [verdict_of[c] for c in cids if c in verdict_of]
    return max(found, key=VERDICTS.index) if found else None


def expand_ids(label: str) -> list[str]:
    out = []
    for a, b in re.findall(r"C(\d+)(?:\s*-\s*C(\d+))?", label):
        out += [f"C{n:02d}" for n in range(int(a), int(b or a) + 1)]
    return out


def toned(spec: dict, verdict_of: dict[str, str]) -> tuple[dict, list[str]]:
    """Colour each node that names claims by the weakest verdict among them, with the verdict as text."""
    used, nodes = set(), []
    for n in spec["nodes"]:
        v = weakest(expand_ids(n["label"]), verdict_of)
        if v:
            used.add(v)
            n = {**n, "tone": TONE[v], "detail": n.get("detail") or v}
        nodes.append(n)
    return {**spec, "nodes": nodes}, [v for v in VERDICTS if v in used]


def glyph_legend(spec: dict, names: dict[str, str]) -> list[dict]:
    glyphs = sorted({n.get("shape", "rect") for n in spec["nodes"]}, key=["rect", "oval", "diamond", "dot"].index)
    return [{"label": names.get(g, g), "glyph": g} for g in glyphs if g in names]


SHAPE_NAMES = {"rect": "module or function", "oval": "input or outside system", "diamond": "decision"}


def walkthrough(spec: dict, anchor: str, legend: list[dict]) -> str:
    return (f"<h4 id={js(anchor)} data-ve-anchor=\"true\">{js(spec['title'])}</h4>\n"
            f"<DiagramWalkthrough layout=\"flow\" title={js(spec['title'])} description={js(spec['description'])} "
            f"nodes={js(spec['nodes'])} edges={js(spec['edges'])} steps={js(spec['steps'])} legend={js(legend)} />")


def claim_rows(data: dict, cids: list[str]) -> list[dict]:
    claims = {c["id"]: c for c in data["claims"]}
    flags = flags_by_claim(data)
    rows = []
    for cid in cids:
        c = claims[cid]
        what = (c.get("plain") or {}).get("what") or c["text"]
        rows.append({"cells": {
            "id": {"text": cid, "href": "#" + claim_anchor(cid)},
            "what": {"text": what, "note": c["text"]} if c.get("plain") else what,
            "verdict": {"text": c["verdict"], "status": TONE[c["verdict"]]},
            "flags": {"badges": flags[cid]} if flags.get(cid) else None}})
    return rows


CLAIM_COLUMNS = [{"key": "id", "label": "ID", "kind": "id", "width": "4.5rem"},
                 {"key": "what", "label": "What it protects"},
                 {"key": "verdict", "label": "Verdict", "kind": "status", "width": "7.5rem"},
                 {"key": "flags", "label": "Flags", "kind": "tags", "width": "10.5rem"}]


def chips(data: dict, cids: list[str]) -> str:
    verdict_of = {c["id"]: c["verdict"] for c in data["claims"]}
    parts = []
    for v in VERDICTS:
        ids = [c for c in cids if verdict_of.get(c) == v]
        if ids:
            parts.append(f"<StatusPill tone=\"{TONE[v]}\">{js(v + ': ' + ', '.join(ids))}</StatusPill>")
    return "<p>" + " ".join(parts) + "</p>" if parts else ""


# ---- Chapter 1: orientation ---------------------------------------------------------------

def orientation(data: dict, extra: dict) -> str:
    lines = extra.get("orientation") or [s.strip() + "." for s in data.get("narrative", "").split(". ")[:5] if s.strip()]
    parts = [f"<p>{inline(t)}</p>" for t in lines]
    if extra.get("architecture"):
        arch = extra["architecture"]
        parts.append(subsection("orientation-architecture", js("Architecture"),
                                f"<DiagramCanvas layout=\"flow\" title={js('Architecture')} description={js(arch.get('description', 'Architecture'))} "
                                f"nodes={js(arch['nodes'])} edges={js(arch['edges'])} legend={js(glyph_legend(arch, SHAPE_NAMES))} />"))
    parts.append(subsection("orientation-words", js("Words to know"), glossary(data)))
    return "\n".join(parts)


# ---- Chapter 2: guided tour ---------------------------------------------------------------

def tour_steps(data: dict, extra: dict) -> list[dict]:
    """The tour from explain.json, else one stop per claim layer. Each claim must appear at a stop."""
    steps = extra.get("tour") or [
        {"id": slug(layer), "title": layer, "text": [], "claims": [c["id"] for c in data["claims"] if c.get("layer", "Claims") == layer]}
        for layer in dict.fromkeys(c.get("layer", "Claims") for c in data["claims"])]
    seen = {cid for s in steps for cid in s.get("claims", [])}
    missing = [c["id"] for c in data["claims"] if c["id"] not in seen]
    unknown = sorted(seen - {c["id"] for c in data["claims"]})
    if missing or unknown:
        tm.fail(f"the tour must show each claim at a step: missing {missing}, unknown {unknown}", 1)
    return steps


def tour(data: dict, extra: dict, repo: str) -> str:
    verdict_of = {c["id"]: c["verdict"] for c in data["claims"]}
    steps = tour_steps(data, extra)
    parts = [f"<p>{js('The tour follows one run in execution order. At each step, the table shows the claims that protect it, and each ID links to its evidence.')}</p>",
             "<ol>" + "".join(f"<li><a href={js('#tour-' + s['id'])}>{js(s['title'].split(':')[0])}</a></li>" for s in steps) + "</ol>"]
    for i, s in enumerate(steps, 1):
        stop = [f"<p>{inline(t)}</p>" for t in s.get("text", [])]
        name = s.get("diagram")
        if name and name in (extra.get("diagrams") or {}):
            spec, used = toned(extra["diagrams"][name], verdict_of)
            legend = ([i for i in VERDICT_LEGEND if i["label"] in used] + glyph_legend(spec, SHAPE_NAMES)
                      + ([{"label": "refused import", "stroke": "dashed"}] if any(e.get("style") == "dashed" for e in spec["edges"]) else []))
            stop.append(f"<h4>{js(spec['title'])}</h4><DiagramCanvas layout=\"flow\" title={js(spec['title'])} "
                         f"description={js(spec['description'])} nodes={js(spec['nodes'])} edges={js(spec['edges'])} legend={js(legend)} />")
        name = s.get("walkthrough")
        if name and name in (extra.get("walkthroughs") or {}):
            spec, used = toned(extra["walkthroughs"][name], verdict_of)
            legend = [i for i in VERDICT_LEGEND if i["label"] in used] + glyph_legend(spec, SHAPE_NAMES)
            stop.append(walkthrough(spec, f"tour-{s['id']}-motion", legend))
        for ref in s.get("code", []):
            got = snippet(repo, data["head"], ref)
            if got:
                code, start = got
                stop.append(f"<CodeBlock language={js(LANG.get(Path(ref['path']).suffix, 'text'))} "
                             f"filename={js(ref['path'] + ':' + str(start))} code={js(code)} />")
        if s.get("claims"):
            stop.append(f"<p><strong>{js('Claims at this step: ')}</strong></p>" + chips(data, s["claims"]))
            stop.append(table(CLAIM_COLUMNS, claim_rows(data, s["claims"]), f"Claims at step {i}"))
        else:
            stop.append(none("No claim in this trust map protects this step."))
        parts.append(subsection("tour-" + s["id"], js(s["title"]), "\n".join(stop), marker=str(i)))
    return "\n".join(parts)


# ---- Chapter 3: confidence ----------------------------------------------------------------

def control_walkthrough(data: dict, spec: dict) -> dict:
    controls = {k["id"]: k for k in data["controls"]}
    verifiers = {v["id"]: v for v in data["verifiers"]}
    nodes, edges, steps, seen = [], [], [], set()
    for kid in spec["controls"]:
        k = controls[kid]
        v = verifiers[k["verifier"]]
        r = k.get("result") or {}
        status = r.get("status", "not run")
        caught = status == (k.get("expect") or {}).get("status", "red")
        nodes.append({"id": f"plant-{kid}", "label": f"{kid}: {k['recipe']}", "shape": "oval"})
        if v["id"] not in seen:
            seen.add(v["id"])
            argv = (v.get("command") or {}).get("argv", [])
            target = argv[-1] if argv and ("/" in argv[-1] or "." in argv[-1]) else "the whole project"
            nodes.append({"id": f"run-{v['id']}", "label": f"{v['id']}: {(v.get('independence') or {}).get('tool', v['kind'])}",
                          "detail": target})
        nodes.append({"id": f"out-{kid}", "label": f"{'caught' if caught else 'missed'}: {status}",
                      "tone": "ok" if caught else "warn", "detail": f"{kid} on {v['id']}"})
        edges += [{"id": f"{kid}-run", "from": f"plant-{kid}", "to": f"run-{v['id']}", "label": "plant, then run"},
                  {"id": f"{kid}-out", "from": f"run-{v['id']}", "to": f"out-{kid}", "label": status}]
        steps += [{"edgeId": f"{kid}-run", "caption": f"{kid} plants a bug in a scratch worktree. {k['description']}"},
                  {"edgeId": f"{kid}-out", "caption": f"{v['id']} went {status}. " + ("The check found the bug." if caught else "The check did not find the bug.")}]
    return {"title": spec["title"], "description": spec["description"], "nodes": nodes, "edges": edges, "steps": steps}


def confidence(data: dict, extra: dict) -> str:
    claims = {c["id"]: c for c in data["claims"]}
    verdict_of = {c["id"]: c["verdict"] for c in data["claims"]}
    parts = [f"<p>{js('This chapter ranks the claims by risk, not by count. The weakest claims with the highest stakes come first, each with the cheapest fix.')}</p>"]
    risks = extra.get("risks") or [{"claims": [c["id"]], "why": c["reason"], "fix": ""}
                                   for c in data["claims"] if c["verdict"] in ("Gap", "Asserted")]
    weak = []
    for r in risks:
        head = "".join(f"<a href={js('#' + claim_anchor(cid))}><code>{js(cid)}</code></a> <StatusPill tone=\"{TONE[verdict_of[cid]]}\">{js(verdict_of[cid])}</StatusPill> "
                       for cid in r["claims"])
        text = " ".join(claims[cid]["text"] for cid in r["claims"])
        what = " ".join((claims[cid].get("plain") or {}).get("what", "") for cid in r["claims"]).strip()
        terms = [("Why it is weak", r["why"], None)] + ([("Cheapest fix", r["fix"], None)] if r.get("fix") else [])
        weak.append(subsection(None, "{<>" + head + js(text) + "</>}",
                               (f"<p>{inline(what)}</p>\n" if what else "") + definitions(terms), level=4))
    parts.append(subsection("confidence-weak", js("The weakest claims first"), "\n".join(weak)))

    for i, spec in enumerate(extra.get("control_walkthroughs") or []):
        motion = control_walkthrough(data, spec)
        legend = [{"label": "caught: the check went red", "tone": "ok"}, {"label": "missed: the check stayed green", "tone": "warn"},
                  {"label": "planted bug", "glyph": "oval"}, {"label": "check", "glyph": "rect"}]
        parts.append(subsection("confidence-controls" + (str(i) if i else ""), js("Verify the verifiers"),
                                f"<p>{inline(spec['description'])}</p>\n" + walkthrough(motion, f"confidence-controls-motion{i}", legend)))

    s = data["summary"]
    proven = [c for c in data["claims"] if c["verdict"] == "Proven"]
    by_layer: dict[str, int] = {}
    for c in proven:
        by_layer[c.get("layer", "Claims")] = by_layer.get(c.get("layer", "Claims"), 0) + 1
    ran = [k for k in data["controls"] if k.get("result")]
    red = [k for k in ran if k["result"].get("status") == "red"]
    solid = [f"{s['Proven']} of {len(data['claims'])} claims are Proven. For each, a control planted a bug and the check went red.",
             "By layer: " + ", ".join(f"{layer} {n}" for layer, n in by_layer.items()) + ".",
             f"{len(red)} of {len(ran)} controls went red in scratch worktrees, with no model call and no cost."]
    if s["Backed"]:
        solid.append(f"{s['Backed']} claims are Backed: the evidence is a record of a past run, and this run did not repeat it.")
    parts.append(subsection("confidence-solid", js("What is solid"), "<ul>" + "".join(f"<li>{js(t)}</li>" for t in solid) + "</ul>"))
    parts.append(verifier_map(data))
    return "\n".join(parts)


def verifier_map(data: dict) -> str:
    verdict_of = {c["id"]: c["verdict"] for c in data["claims"]}
    layer_of = {c["id"]: c.get("layer", "Claims") for c in data["claims"]}
    kinds: dict[str, dict] = {}
    links: dict[tuple[str, str], set[str]] = {}
    for v in data["verifiers"]:
        k = kinds.setdefault(v["kind"], {"n": 0, "guess": False})
        k["n"] += 1
        k["guess"] |= v["tier"] == "guess"
        for cid in v["claims"]:
            if cid in layer_of:
                links.setdefault((v["kind"], layer_of[cid]), set()).add(cid)
    layers = list(dict.fromkeys(layer_of.values()))
    layer_verdict = {layer: weakest([c for c, lay in layer_of.items() if lay == layer], verdict_of) for layer in layers}
    kind_ids = {kind: f"k{i}" for i, kind in enumerate(kinds)}
    layer_ids = {layer: f"l{i}" for i, layer in enumerate(layers)}
    nodes = [{"id": kind_ids[kind], "label": f"{kind} ({k['n']})", "shape": glyph(kind),
              "detail": "guess tier" if k["guess"] else "fact tier", **({"stroke": "dashed"} if k["guess"] else {})}
             for kind, k in kinds.items()]
    covered = {layer for _, layer in links}
    nodes += [{"id": layer_ids[layer], "label": layer, "tone": TONE[layer_verdict[layer]], "detail": f"weakest: {layer_verdict[layer]}"}
              for layer in layers if layer in covered]
    edges = [{"from": kind_ids[kind], "to": layer_ids[layer], "label": f"{len(cids)} claims" if len(cids) > 1 else "1 claim"}
             for (kind, layer), cids in links.items()]
    used = [v for v in VERDICTS if v in {layer_verdict[layer] for layer in covered}]
    glyphs = sorted({glyph(k) for k in kinds}, key=list(GLYPH_FAMILY).index)
    legend = ([i for i in VERDICT_LEGEND if i["label"] in used] + [{"label": GLYPH_FAMILY[g], "glyph": g} for g in glyphs]
              + [{"label": "fact tier", "stroke": "solid"}]
              + ([{"label": "guess tier", "stroke": "dashed"}] if any(k["guess"] for k in kinds.values()) else []))
    uncovered = [layer for layer in layers if layer not in covered]
    parts = [f"<p>{js('Each verifier kind, with an edge to each claim layer that it backs. A layer takes the colour and the word of its weakest verdict.' + (' No verifier backs: ' + ', '.join(uncovered) + '.' if uncovered else ''))}</p>"
             f"<DiagramCanvas layout=\"flow\" title={js('From verifiers to claims')} description={js('Verifier kinds and the claim layers they back.')} "
             f"nodes={js(nodes)} edges={js(edges)} legend={js(legend)} />"]
    controls: dict[str, list[str]] = {}
    for k in data["controls"]:
        controls.setdefault(k["verifier"], []).append(f"{k['id']} {k['recipe']}: {(k.get('result') or {}).get('status', 'not run')}")
    vflags: dict[str, list[dict]] = {}
    for f in data["flags"]:
        vflags.setdefault(f["subject"], []).append({"label": f["flag"], "tone": FLAG_TONE.get(f["flag"], "warn")})
    columns = [{"key": "id", "label": "Verifier", "kind": "id", "width": "5.5rem"},
               {"key": "kind", "label": "Kind", "kind": "tags", "width": "9.5rem"},
               {"key": "tier", "label": "Tier", "kind": "tags", "width": "5.5rem"},
               {"key": "state", "label": "State", "kind": "status", "width": "8.5rem"},
               {"key": "claims", "label": "Claims", "kind": "tags", "width": "9rem"},
               {"key": "controls", "label": "Controls"}]
    rows = [{"id": f"verifier-{slug(v['id'])}", "cells": {
        "id": {"text": v["id"], **({"badges": vflags[v["id"]]} if v["id"] in vflags else {})},
        "kind": {"badges": [{"label": v["kind"], "glyph": glyph(v["kind"])}]},
        "tier": {"badges": [{"label": v["tier"], "stroke": "dashed" if v["tier"] == "guess" else "solid"}]},
        "state": {"text": v.get("state", "unknown"), "status": STATE_TONE.get(v.get("state", ""), "neutral")},
        "claims": {"badges": [{"label": cid, "tone": TONE.get(verdict_of.get(cid, ""), "neutral")} for cid in v["claims"]]},
        "controls": "; ".join(controls.get(v["id"], [])) or None}} for v in data["verifiers"]]
    parts.append(f"<h4>{js('Verifier map')}</h4>\n" + table(columns, rows, "Verifier map"))
    return subsection("confidence-map", js("From verifiers to claims"), "\n".join(parts))


# ---- Chapter 4: evidence ------------------------------------------------------------------

def edit_block(edit: dict) -> str:
    lang = LANG.get(Path(edit["path"]).suffix, "text")
    name = js(edit["path"])
    if edit["op"] == "replace" and edit.get("find") != edit.get("replace"):
        return f"<DiffBlock language={js(lang)} filename={name} before={js(edit['find'])} after={js(edit['replace'])} />"
    if edit["op"] == "append" and edit.get("text"):
        return f"<DiffBlock language={js(lang)} filename={name} before={js('')} after={js(edit['text'])} />"
    detail = ", ".join(f"{k} {v}" for k, v in edit.items() if k not in ("op", "path"))
    return f"<p><code>{js(edit['op'])}</code>{js(' ' + edit['path'] + (': ' + detail if detail else ''))}</p>"


def evidence(data: dict, repo: str, steps: list[dict]) -> str:
    step_of = {cid: s for s in steps for cid in s.get("claims", [])}
    by_claim: dict[str, list[dict]] = {}
    for v in data["verifiers"]:
        for cid in v["claims"]:
            by_claim.setdefault(cid, []).append(v)
    controls: dict[str, list[dict]] = {}
    for k in data["controls"]:
        controls.setdefault(k["verifier"], []).append(k)
    parts = [f"<p>{js('Each claim with its plain text, its code at the head, each verifier, and each control with its edit and its output.')}</p>",
             subsection("evidence-index", js("Claim index"), table(CLAIM_COLUMNS, claim_rows(data, [c["id"] for c in data["claims"]]), "Claim index"))]
    for verdict, claims in by_verdict(data):
        group = [intro(data, verdict)]
        for c in claims:
            body = []
            step = step_of.get(c["id"])
            if step:
                body.append(f"<p><a href={js('#tour-' + step['id'])}>{js('Tour step: ' + step['title'].split(':')[0])}</a></p>")
            plain = c.get("plain")
            if plain:
                body.append(definitions([("What it is", plain["what"], None), ("How it is proven", plain["proof"], None)]
                                        + ([("Warning", plain["warning"], "warn")] if plain.get("warning") else [])))
            body.append(f"<p>{js('Reason: ' + c['reason'] + ' Source: ' + c['source'] + '.')}</p>")
            for ref in c.get("code", []):
                got = snippet(repo, data["head"], ref)
                if got:
                    code, start = got
                    body.append(f"<CodeBlock language={js(LANG.get(Path(ref['path']).suffix, 'text'))} "
                                f"filename={js(ref['path'] + ':' + str(start))} code={js(code)} />")
            for v in by_claim.get(c["id"], []):
                body.append(f"<p><strong>{js(v['id'] + ':')}</strong>{js(' ' + v['description'] + ' Provenance: ' + v['provenance'])}</p>")
                if "recorded" in v:
                    body.append(f"<TerminalBlock title={js('Recorded: ' + v['recorded']['source'])} content={js(v['recorded']['result'])} />")
                if "command" in v:
                    b = v.get("baseline") or {}
                    body.append(f"<CodeBlock language=\"bash\" filename={js('At the PR head: ' + b.get('status', 'not run'))} "
                                f"code={js('$ ' + ' '.join(v['command']['argv']))} />")
                    if b.get("output_tail"):
                        body.append(f"<TerminalBlock title={js('Output at the PR head')} content={js(b['output_tail'])} />")
                for k in controls.get(v["id"], []):
                    r = k.get("result") or {}
                    body.append(f"<p><strong>{js('Control ' + k['id'] + ' (' + k['recipe'] + '): ' + r.get('status', 'not run') + '.')}</strong>{js(' ' + k['description'])}</p>")
                    body += [edit_block(e) for e in k["edits"]]
                    tail = r.get("output_tail", r.get("note", ""))
                    if tail:
                        body.append(f"<TerminalBlock title={js('Control ' + k['id'] + ' output')} content={js(tail)} />")
            title = f"{{<><code>{js(c['id'])}</code> <StatusPill tone=\"{TONE[c['verdict']]}\">{js(c['verdict'])}</StatusPill> {js(c['text'])}</>}}"
            group.append(subsection(claim_anchor(c["id"]), title, "\n".join(body), level=4))
        parts.append(subsection("evidence-" + slug(verdict), js(f"{verdict} ({len(claims)})"), "\n".join(p for p in group if p)))
    return "\n".join(p for p in parts if p)


# ---- Chapters 5 and 6 ---------------------------------------------------------------------

def bullets(items: list[str], empty: str) -> str:
    if not items:
        return f"<p>{js(empty)}</p>"
    return "<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>"


def tradeoffs(extra: dict) -> str:
    return "\n".join([
        subsection("tradeoffs-list", js("Trade-offs"), bullets(extra.get("tradeoffs", []), "No trade-offs recorded.")),
        subsection("tradeoffs-concerns", js("Concerns"), bullets(extra.get("concerns", []), "No concerns recorded.")),
        subsection("tradeoffs-verifications", js("Verifications of this explainer"), bullets(extra.get("verifications", []), "No verifications recorded."))])


def exercises() -> str:
    return none("This chapter is a placeholder. The learning app fills it.")


def anchors(items: list[tuple[str, str]]) -> str:
    return js([{"id": i, "label": label} for i, label in items])


CHAPTERS = ["orientation", "tour", "confidence", "evidence", "tradeoffs", "exercises"]
CHAPTER_COMPONENTS = "DiagramCanvas, DiagramWalkthrough, DataTable, StatusPill, CodeBlock, DiffBlock, TerminalBlock, DefinitionList, Definition, Subsection"


def chapter_file(repo_path: str, name: str, body: str) -> str:
    """One self-contained MDX unit: its own imports and its content, so an app can embed it."""
    return (f"{{/* understando chapter: {name}. scripts/explain.py writes it from trust-map.json and explain.json. */}}\n"
            f"import {{ {CHAPTER_COMPONENTS} }} from '{repo_path}/visual-explainer-mdx/components';\n\n{body}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--extra")
    ap.add_argument("--runtime")
    ap.add_argument("--explainer-url")
    args = ap.parse_args()
    data = tm.load(args.map)
    errors = tm.validate(data)
    if errors or "summary" not in data:
        tm.fail("run scripts/verdicts.py first; the map is invalid or has no verdicts", 1)
    extra = tm.load(args.extra) if args.extra else {}
    out = Path(args.out)
    (out / "chapters").mkdir(parents=True, exist_ok=True)
    (out / "pr-section.md").write_text(pr_section(data, extra, args.explainer_url), encoding="utf-8")
    runtime = runtime_path(args.runtime)
    steps = tour_steps(data, extra)
    bodies = {"orientation": orientation(data, extra), "tour": tour(data, extra, args.repo),
              "confidence": confidence(data, extra), "evidence": evidence(data, args.repo, steps),
              "tradeoffs": tradeoffs(extra), "exercises": exercises()}
    for i, name in enumerate(CHAPTERS, 1):
        (out / "chapters" / f"{i:02d}-{name}.mdx").write_text(chapter_file(runtime, name, bodies[name]), encoding="utf-8")
    groups = [(slug(v), f"{v} ({len(cs)})") for v, cs in by_verdict(data)]
    nav = {
        "ORIENTATION_ANCHORS": [("orientation-architecture", "Architecture")] * bool(extra.get("architecture")) + [("orientation-words", "Words to know")],
        "TOUR_ANCHORS": [("tour-" + s["id"], s["title"].split(":")[0]) for s in steps],
        "CONFIDENCE_ANCHORS": [("confidence-weak", "Weakest claims")] + [("confidence-controls", "Verify the verifiers")] * bool(extra.get("control_walkthroughs"))
                              + [("confidence-solid", "What is solid"), ("confidence-map", "Verifiers to claims")],
        "EVIDENCE_ANCHORS": [("evidence-index", "Claim index")] + [("evidence-" + i, label) for i, label in groups],
        "TRADEOFFS_ANCHORS": [("tradeoffs-list", "Trade-offs"), ("tradeoffs-concerns", "Concerns"), ("tradeoffs-verifications", "Verifications")],
    }
    title = f"PR #{data.get('pr')}: " + (data.get("title") or data["repo"])
    s = data["summary"]
    summary = (f"{data['repo']}, head {data['head'][:10]}. A guided tour of the change, then how far to trust it: "
               + ", ".join(f"{s[v]} {v}" for v in VERDICTS) + ".")
    filled = (tm.ROOT / "templates" / "three-level.mdx").read_text(encoding="utf-8")
    filled = filled.replace("{{REPO}}", runtime).replace("{{TITLE}}", json.dumps(title)).replace("{{SUMMARY}}", json.dumps(summary))
    for key, items in nav.items():
        filled = filled.replace("{{" + key + "}}", anchors(items))
    (out / "explainer.mdx").write_text(filled, encoding="utf-8")
    print(f"wrote {out / 'pr-section.md'}")
    print(f"wrote {out / 'explainer.mdx'} and {len(CHAPTERS)} chapters in {out / 'chapters'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
