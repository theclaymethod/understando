#!/usr/bin/env python3
"""Build the PR-body section and the three-level explainer source from a trust map.

    python3 scripts/explain.py --map trust-map.json --repo <git repo> --out DIR \
        [--extra explain.json] [--runtime REPO] [--explainer-url URL]

Writes:
  DIR/pr-section.md    the short PR-body section: one diagram, the claims-and-verdicts table,
                       and short bullets
  DIR/explainer.mdx    the three-level explainer source (templates/three-level.mdx, filled)

--runtime is the Artifacture checkout. $UNDERSTANDO_VE_RUNTIME sets it too. The default asks the
visual-explainer CLI:
`node ~/.claude/skills/visual-explainer/scripts/artifacture.mjs path`.
Export the HTML after this script with the visual-explainer CLI (see commands/explain.md).

explain.json (optional, written by the agent) holds what the trust map does not:
  {"architecture": {"description": str, "nodes": [...], "edges": [...]},
   "codepath": {"description": str, "nodes": [...], "edges": [...]},
   "tradeoffs": [str], "concerns": [str], "verifications": [str], "bullets": [str]}
Nodes and edges use the DiagramCanvas shape: {id, label} and {from, to, label?}.
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


def row_anchor(cid: str) -> str:
    return f"verdict-{slug(cid)}"


def layer_anchor(layer: str) -> str:
    return f"layer-{slug(layer)}"


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


def table(columns: list[dict], rows: list[dict], label: str) -> str:
    return f"<DataTable label={js(label)} columns={js(columns)} rows={js(rows)} />"


def diagram(spec: dict | None, title: str, anchor: str, legend: list[dict]) -> str:
    if not spec:
        return ""
    return (f"<div id={js(anchor)} data-ve-anchor=\"true\"><h3>{js(title)}</h3>"
            f"<DiagramCanvas layout=\"flow\" title={js(title)} description={js(spec.get('description', title))} "
            f"nodes={js(spec['nodes'])} edges={js(spec['edges'])} legend={js(legend)} /></div>")


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
    body = "".join(f"<dt>{js(g['term'])}</dt><dd>{inline(g['meaning'])}</dd>" for g in items)
    return f"<dl className=\"ux-glossary\">{body}</dl>"


def high(data: dict) -> str:
    s = data["summary"]
    parts = [f"<p>{js(str(len(data['claims'])) + ' claims. Each verdict links to its diagram and its evidence.')}</p>",
             "<p className=\"ux-pills\">" + " ".join(
                 f"<StatusPill tone=\"{TONE[v]}\">{js(str(s[v]) + ' ' + v)}</StatusPill>" for v in VERDICTS) + "</p>"]
    loud = [f for f in data["flags"] if f.get("loud")]
    if loud:
        parts.append("<Callout>" + "".join(f"<p><strong>{js(f['flag'] + ':')}</strong>{js(' ' + f['detail'])}</p>" for f in loud) + "</Callout>")
    flags = flags_by_claim(data)
    columns = [{"key": "id", "label": "ID", "kind": "id", "width": "4.5rem"},
               {"key": "claim", "label": "Claim"},
               {"key": "layer", "label": "Layer", "width": "9.5rem"},
               {"key": "verdict", "label": "Verdict", "kind": "status", "width": "7.5rem"},
               {"key": "flags", "label": "Flags", "kind": "tags", "width": "10.5rem"}]
    for verdict, claims in by_verdict(data):
        parts.append(f"<h3 id={js('high-' + slug(verdict))} data-ve-anchor=\"true\">{js(f'{verdict} ({len(claims)})')}</h3>")
        parts.append(intro(data, verdict))
        rows = [{"id": row_anchor(c["id"]), "cells": {
            "id": {"text": c["id"], "href": "#" + claim_anchor(c["id"])},
            "claim": {"text": c["text"], **({"note": c["plain"]["what"]} if c.get("plain") else {})},
            "layer": {"text": c.get("layer", ""), "href": "#" + layer_anchor(c.get("layer", "Claims"))},
            "verdict": {"text": c["verdict"], "status": TONE[c["verdict"]]},
            "flags": {"badges": flags.get(c["id"], [])} if flags.get(c["id"]) else None}}
            for c in claims]
        parts.append(table(columns, rows, f"{verdict} claims"))
    parts.append(f"<p>{js('Select an ID to see its code and evidence. Select a layer to see its row in the verdict map.')}</p>")
    return "\n".join(p for p in parts if p)


def weakest(cids: list[str], verdict_of: dict[str, str]) -> str | None:
    found = [verdict_of[c] for c in cids if c in verdict_of]
    return max(found, key=VERDICTS.index) if found else None


def expand_ids(label: str) -> list[str]:
    out = []
    for a, b in re.findall(r"C(\d+)(?:\s*-\s*C(\d+))?", label):
        out += [f"C{n:02d}" for n in range(int(a), int(b or a) + 1)]
    return out


def toned(spec: dict | None, verdict_of: dict[str, str]) -> tuple[dict | None, set[str]]:
    """Colour each node that names claims by the weakest verdict among them, with the verdict as text."""
    if not spec:
        return None, set()
    used, nodes = set(), []
    for n in spec["nodes"]:
        v = weakest(expand_ids(n["label"]), verdict_of)
        if v:
            used.add(v)
            n = {**n, "tone": TONE[v], "detail": n.get("detail") or v}
        nodes.append(n)
    return {**spec, "nodes": nodes}, used


def medium(data: dict, extra: dict) -> str:
    verdict_of = {c["id"]: c["verdict"] for c in data["claims"]}
    parts = []
    if extra.get("architecture"):
        arch = extra["architecture"]
        glyphs = sorted({n.get("shape", "rect") for n in arch["nodes"]})
        names = {"rect": "module or function", "oval": "input or outside system", "diamond": "decision"}
        parts.append(diagram(arch, "Architecture", "medium-architecture",
                             [{"label": names.get(g, g), "glyph": g} for g in glyphs]))
    if extra.get("codepath"):
        spec, used = toned(extra["codepath"], verdict_of)
        legend = [i for i in VERDICT_LEGEND if i["label"] in used] + [{"label": "decision", "glyph": "diamond"}]
        parts.append(diagram(spec, "Code path", "medium-codepath", legend))
        parts.append(f"<p>{js('A coloured step names claims. Its colour and its word are the weakest verdict among those claims.')}</p>")

    layers: dict[str, dict[str, list[str]]] = {}
    for c in data["claims"]:
        layers.setdefault(c.get("layer", "Claims"), {v: [] for v in VERDICTS})[c["verdict"]].append(c["id"])
    nodes = [{"id": f"l{i}", "label": layer, "detail": f"{sum(map(len, n.values()))} claims"}
             for i, (layer, n) in enumerate(layers.items())]
    nodes += [{"id": v, "label": v, "shape": "oval", "tone": TONE[v], "detail": f"{data['summary'][v]} claims"}
              for v in VERDICTS if data["summary"][v]]
    edges = [{"from": f"l{i}", "to": v, "label": str(len(ids))}
             for i, (layer, n) in enumerate(layers.items()) for v, ids in n.items() if ids]
    parts.append(diagram({"description": "Each claim layer, with an edge to each verdict. The edge label is the claim count.",
                          "nodes": nodes, "edges": edges},
                         "Verdicts by layer", "medium-verdicts", VERDICT_LEGEND))
    columns = ([{"key": "layer", "label": "Layer", "width": "11rem"}]
               + [{"key": v, "label": v, "kind": "number", "width": "5.5rem"} for v in VERDICTS]
               + [{"key": "claims", "label": "Claims"}])
    rows = [{"id": layer_anchor(layer), "cells": {
        "layer": layer, **{v: len(n[v]) for v in VERDICTS},
        "claims": {"badges": [{"label": cid, "tone": TONE[v]} for v in VERDICTS for cid in n[v]]}}}
        for layer, n in layers.items()]
    parts.append(table(columns, rows, "Claims by layer and verdict"))
    parts.append(f"<p>{js('Each claim ID in the table links to its code and evidence below.')}</p>")
    parts.append(claim_links(layers))

    kinds: dict[str, dict] = {}
    claim_verdicts: dict[str, dict[str, int]] = {}
    for v in data["verifiers"]:
        k = kinds.setdefault(v["kind"], {"n": 0, "guess": False})
        k["n"] += 1
        k["guess"] |= v["tier"] == "guess"
        for cid in v["claims"]:
            if cid in verdict_of:
                claim_verdicts.setdefault(v["kind"], {}).setdefault(verdict_of[cid], 0)
                claim_verdicts[v["kind"]][verdict_of[cid]] += 1
    knodes = [{"id": f"k{i}", "label": f"{kind} ({k['n']})", "shape": glyph(kind),
               "detail": "guess tier" if k["guess"] else "fact tier", **({"stroke": "dashed"} if k["guess"] else {})}
              for i, (kind, k) in enumerate(kinds.items())]
    vused = sorted({v for counts in claim_verdicts.values() for v in counts}, key=VERDICTS.index)
    knodes += [{"id": v, "label": v, "shape": "oval", "tone": TONE[v]} for v in vused]
    kedges = [{"from": f"k{i}", "to": v, "label": str(n)}
              for i, kind in enumerate(kinds) for v, n in sorted(claim_verdicts.get(kind, {}).items(), key=lambda x: VERDICTS.index(x[0]))]
    glyphs_used = sorted({glyph(k) for k in kinds}, key=list(GLYPH_FAMILY).index)
    klegend = ([i for i in VERDICT_LEGEND if i["label"] in vused]
               + [{"label": GLYPH_FAMILY[g], "glyph": g} for g in glyphs_used]
               + [{"label": "fact tier", "stroke": "solid"}]
               + ([{"label": "guess tier", "stroke": "dashed"}] if any(k["guess"] for k in kinds.values()) else []))
    parts.append(diagram({"description": "Each verifier kind, with an edge to the verdicts of the claims that it backs. The edge label is the claim count.",
                          "nodes": knodes, "edges": kedges},
                         "Verifier kinds and the verdicts they back", "medium-kinds", klegend))

    controls: dict[str, list[str]] = {}
    for k in data["controls"]:
        status = (k.get("result") or {}).get("status", "not run")
        controls.setdefault(k["verifier"], []).append(f"{k['id']} {k['recipe']}: {status}")
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
    parts.append(f"<div id=\"medium-verifiers\" data-ve-anchor=\"true\"><h3>{js('Verifier map')}</h3>"
                 f"<p>{js('Each verifier, its kind, its tier, its state, the claims it backs and its controls. Kind uses the glyph of the diagram above. A dashed, hatched tier is a guess.')}</p>"
                 + table(columns, rows, "Verifier map") + "</div>")
    return "\n".join(p for p in parts if p)


def claim_links(layers: dict[str, dict[str, list[str]]]) -> str:
    items = "".join(
        f"<li><strong>{js(layer + ':')}</strong> " + ", ".join(
            f"<a href={js('#' + claim_anchor(cid))}>{js(cid)}</a>" for v in VERDICTS for cid in n[v]) + "</li>"
        for layer, n in layers.items())
    return f"<ul className=\"ux-claim-links\">{items}</ul>"


def edit_block(edit: dict) -> str:
    lang = LANG.get(Path(edit["path"]).suffix, "text")
    name = js(edit["path"])
    if edit["op"] == "replace" and edit.get("find") != edit.get("replace"):
        return f"<DiffBlock language={js(lang)} filename={name} before={js(edit['find'])} after={js(edit['replace'])} />"
    if edit["op"] == "append" and edit.get("text"):
        return f"<DiffBlock language={js(lang)} filename={name} before={js('')} after={js(edit['text'])} />"
    detail = ", ".join(f"{k} {v}" for k, v in edit.items() if k not in ("op", "path"))
    return f"<p><code>{js(edit['op'])}</code>{js(' ' + edit['path'] + (': ' + detail if detail else ''))}</p>"


def low(data: dict, repo: str) -> str:
    by_claim: dict[str, list[dict]] = {}
    for v in data["verifiers"]:
        for cid in v["claims"]:
            by_claim.setdefault(cid, []).append(v)
    controls: dict[str, list[dict]] = {}
    for k in data["controls"]:
        controls.setdefault(k["verifier"], []).append(k)
    parts = []
    for verdict, claims in by_verdict(data):
        parts.append(f"<h3 id={js('low-' + slug(verdict))} data-ve-anchor=\"true\">{js(f'{verdict} ({len(claims)})')}</h3>")
        parts.append(intro(data, verdict))
        for c in claims:
            parts.append(f"<article className=\"ux-claim\" id={js(claim_anchor(c['id']))} data-ve-anchor=\"true\">")
            parts.append(f"<h4><code>{js(c['id'])}</code> <StatusPill tone=\"{TONE[c['verdict']]}\">{js(c['verdict'])}</StatusPill> {js(c['text'])}</h4>")
            parts.append(f"<p className=\"ux-drill\"><a href={js('#' + row_anchor(c['id']))}>{js('Verdict row')}</a>"
                         f"<a href={js('#' + layer_anchor(c.get('layer', 'Claims')))}>{js('Layer in the verdict map')}</a></p>")
            plain = c.get("plain")
            if plain:
                rows = [("What it is", plain["what"]), ("How it is proven", plain["proof"])]
                body = "".join(f"<dt>{js(k)}</dt><dd>{inline(t)}</dd>" for k, t in rows)
                if plain.get("warning"):
                    body += f"<dt className=\"ux-warning\">{js('Warning')}</dt><dd className=\"ux-warning\">{inline(plain['warning'])}</dd>"
                parts.append(f"<dl className=\"ux-plain\">{body}</dl>")
            parts.append(f"<p>{js('Reason: ' + c['reason'] + ' Source: ' + c['source'] + '.')}</p>")
            for ref in c.get("code", []):
                got = snippet(repo, data["head"], ref)
                if got:
                    code, start = got
                    parts.append(f"<CodeBlock language={js(LANG.get(Path(ref['path']).suffix, 'text'))} "
                                 f"filename={js(ref['path'] + ':' + str(start))} code={js(code)} />")
            for v in by_claim.get(c["id"], []):
                parts.append(f"<p><strong>{js(v['id'] + ':')}</strong>{js(' ' + v['description'] + ' Provenance: ' + v['provenance'])}</p>")
                if "recorded" in v:
                    parts.append(f"<TerminalBlock title={js('Recorded: ' + v['recorded']['source'])} content={js(v['recorded']['result'])} />")
                if "command" in v:
                    b = v.get("baseline") or {}
                    parts.append(f"<CodeBlock language=\"bash\" filename={js('At the PR head: ' + b.get('status', 'not run'))} "
                                 f"code={js('$ ' + ' '.join(v['command']['argv']))} />")
                    if b.get("output_tail"):
                        parts.append(f"<TerminalBlock title={js('Output at the PR head')} content={js(b['output_tail'])} />")
                for k in controls.get(v["id"], []):
                    r = k.get("result") or {}
                    parts.append(f"<p><strong>{js('Control ' + k['id'] + ' (' + k['recipe'] + '): ' + r.get('status', 'not run') + '.')}</strong>{js(' ' + k['description'])}</p>")
                    parts += [edit_block(e) for e in k["edits"]]
                    tail = r.get("output_tail", r.get("note", ""))
                    if tail:
                        parts.append(f"<TerminalBlock title={js('Control ' + k['id'] + ' output')} content={js(tail)} />")
            parts.append("</article>")
    return "\n".join(p for p in parts if p)


def anchors(items: list[tuple[str, str]]) -> str:
    return js([{"id": i, "label": label} for i, label in items])


def bullets(items: list[str], empty: str) -> str:
    if not items:
        return f"<p>{js(empty)}</p>"
    return "<ul>" + "".join(f"<li>{js(i)}</li>" for i in items) + "</ul>"


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
    out.mkdir(parents=True, exist_ok=True)
    (out / "pr-section.md").write_text(pr_section(data, extra, args.explainer_url), encoding="utf-8")
    template = (tm.ROOT / "templates" / "three-level.mdx").read_text(encoding="utf-8")
    title = f"Trust map for #{data.get('pr')}"
    s = data["summary"]
    summary = (f"{data['repo']}: {data.get('title', '')}. " if data.get("title") else f"{data['repo']}. ")
    summary += ", ".join(f"{s[v]} {v}" for v in VERDICTS) + f". Head {data['head'][:10]}."
    groups = [(slug(v), f"{v} ({len(cs)})") for v, cs in by_verdict(data)]
    high_anchors = [("high-" + i, label) for i, label in groups]
    low_anchors = [("low-" + i, label) for i, label in groups]
    medium_anchors = [(i, label) for i, label in [("medium-architecture", "Architecture"), ("medium-codepath", "Code path")]
                      if extra.get(i.split("-")[1])]
    medium_anchors += [("medium-verdicts", "Verdicts by layer"), ("medium-kinds", "Verifier kinds"), ("medium-verifiers", "Verifier map")]
    filled = (template.replace("{{REPO}}", runtime_path(args.runtime))
              .replace("{{TITLE}}", json.dumps(title)).replace("{{SUMMARY}}", json.dumps(summary))
              .replace("{{HIGH_ANCHORS}}", anchors(high_anchors)).replace("{{MEDIUM_ANCHORS}}", anchors(medium_anchors))
              .replace("{{LOW_ANCHORS}}", anchors(low_anchors))
              .replace("{{GLOSSARY}}", glossary(data))
              .replace("{{HIGH}}", high(data)).replace("{{MEDIUM}}", medium(data, extra))
              .replace("{{LOW}}", low(data, args.repo))
              .replace("{{TRADEOFFS}}", bullets(extra.get("tradeoffs", []), "No trade-offs recorded."))
              .replace("{{CONCERNS}}", bullets(extra.get("concerns", []), "No concerns recorded."))
              .replace("{{VERIFICATIONS}}", bullets(extra.get("verifications", []), "No verifications recorded.")))
    (out / "explainer.mdx").write_text(filled, encoding="utf-8")
    print(f"wrote {out / 'pr-section.md'}")
    print(f"wrote {out / 'explainer.mdx'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
