#!/usr/bin/env python3
"""Build the PR-body section and the three-level explainer source from a trust map.

    python3 scripts/explain.py --map trust-map.json --repo <git repo> --out DIR \
        [--extra explain.json] [--runtime REPO] [--explainer-url URL]

Writes:
  DIR/pr-section.md    the short PR-body section: one diagram, the claims-and-verdicts table,
                       and short bullets
  DIR/explainer.mdx    the three-level explainer source (templates/three-level.mdx, filled)

--runtime is the Artifacture checkout. The default asks the visual-explainer CLI:
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


def js(value, escape: bool = True) -> str:
    """A JSX expression that holds `value` as data, so MDX never parses it as markup.

    CodeBlock reads its `code` prop as raw text, so a `\\u003c` escape would show. Pass
    escape=False for code. The MDX preflight still needs the escape before a capital letter."""
    text = json.dumps(value, ensure_ascii=False)
    if not escape and not re.search(r"<[A-Z]", text):
        return "{" + text + "}"
    # Escape < and >. JSON syntax holds them only inside strings, and the MDX preflight
    # must never read code text as a component tag.
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
    if explicit:
        return explicit
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


CELL = "{{padding: '6px 10px', borderBottom: '1px solid var(--ve-border, #ddd)', verticalAlign: 'top', textAlign: 'left'}}"
TIGHT = "{{padding: '6px 10px', borderBottom: '1px solid var(--ve-border, #ddd)', verticalAlign: 'top', textAlign: 'left', whiteSpace: 'nowrap'}}"


def table(rows: list[list[str]], head: list[str], nowrap: tuple[int, ...] = (0,)) -> str:
    def style(i: int) -> str:
        return TIGHT if i in nowrap else CELL
    cells = "".join(f"<th style={style(i)}>{js(h)}</th>" for i, h in enumerate(head))
    body = "".join("<tr>" + "".join(f"<td style={style(i)}>{js(c)}</td>" for i, c in enumerate(r)) + "</tr>"
                   for r in rows)
    return (f"<div style={{{{overflowX: 'auto', maxWidth: '100%'}}}}>"
            f"<table style={{{{width: '100%', borderCollapse: 'collapse'}}}}>"
            f"<thead><tr>{cells}</tr></thead><tbody>{body}</tbody></table></div>")


def diagram(spec: dict | None, title: str) -> str:
    if not spec:
        return ""
    return (f"<DiagramCanvas layout=\"flow\" title={js(title)} description={js(spec.get('description', title))} "
            f"nodes={js(spec['nodes'])} edges={js(spec['edges'])} />")


def high(data: dict) -> str:
    s = data["summary"]
    counts = ", ".join(f"{s[v]} {v}" for v in VERDICTS)
    parts = [f"<p>{js(str(len(data['claims'])) + ' claims: ' + counts + '.')}</p>"]
    loud = [f for f in data["flags"] if f.get("loud")]
    if loud:
        parts.append("<Callout>" + "".join(f"<p><strong>{js(f['flag'] + ':')}</strong>{js(' ' + f['detail'])}</p>" for f in loud) + "</Callout>")
    parts.append(table([[c["id"], c.get("layer", ""), c["text"], c["verdict"]] for c in data["claims"]],
                       ["ID", "Layer", "Claim", "Verdict"], nowrap=(0, 1, 3)))
    parts.append(f"<p>{js('Proven: a fact-tier verifier went red on a planted defect. Backed: a verifier exists, but no control went red, or a model judged it. Asserted: only the PR text says so. Gap: no verifier and no statement.')}</p>")
    return "\n".join(parts)


def medium(data: dict, extra: dict) -> str:
    parts = []
    if extra.get("architecture"):
        parts.append(diagram(extra["architecture"], "Architecture"))
    if extra.get("codepath"):
        parts.append(diagram(extra["codepath"], "Code path"))
    layers: dict[str, dict[str, int]] = {}
    for c in data["claims"]:
        layers.setdefault(c.get("layer", "Claims"), {v: 0 for v in VERDICTS})[c["verdict"]] += 1
    parts.append(f"<p>{js('Claims by layer and verdict.')}</p>")
    parts.append(table([[layer] + [str(n[v]) for v in VERDICTS] for layer, n in layers.items()],
                       ["Layer"] + VERDICTS, nowrap=(0, 1, 2, 3, 4)))
    controls: dict[str, list[str]] = {}
    for k in data["controls"]:
        status = (k.get("result") or {}).get("status", "not run")
        controls.setdefault(k["verifier"], []).append(f"{k['id']} {k['recipe']}: {status}")
    rows = [[v["id"], v["kind"], v["tier"], v.get("state", ""), ", ".join(v["claims"]),
             "; ".join(controls.get(v["id"], [])) or "none"] for v in data["verifiers"]]
    parts.append(f"<p>{js('The verifier map: each verifier, its state, the claims it backs and its controls.')}</p>")
    parts.append(table(rows, ["Verifier", "Kind", "Tier", "State", "Claims", "Controls"], nowrap=(0, 1, 2, 3, 4)))
    return "\n".join(p for p in parts if p)


def low(data: dict, repo: str) -> str:
    by_claim: dict[str, list[dict]] = {}
    for v in data["verifiers"]:
        for cid in v["claims"]:
            by_claim.setdefault(cid, []).append(v)
    controls: dict[str, list[dict]] = {}
    for k in data["controls"]:
        controls.setdefault(k["verifier"], []).append(k)
    parts = []
    for c in data["claims"]:
        parts.append(f"<h3>{js(c['id'] + ' ' + c['verdict'] + ': ' + c['text'])}</h3>")
        parts.append(f"<p>{js(c['reason'] + ' Source: ' + c['source'] + '.')}</p>")
        for ref in c.get("code", []):
            got = snippet(repo, data["head"], ref)
            if got:
                code, start = got
                name = f"{ref['path']}:{start}"
                parts.append(f"<CodeBlock language={js(LANG.get(Path(ref['path']).suffix, 'text'))} "
                             f"filename={js(name)} code={js(code, escape=False)} />")
        for v in by_claim.get(c["id"], []):
            parts.append(f"<p><strong>{js(v['id'] + ':')}</strong>{js(' ' + v['description'] + ' Provenance: ' + v['provenance'])}</p>")
            if "recorded" in v:
                parts.append(f"<TerminalBlock title={js('Recorded: ' + v['recorded']['source'])} content={js(v['recorded']['result'])} />")
            if "command" in v:
                cmd = " ".join(v["command"]["argv"])
                b = v.get("baseline") or {}
                parts.append(f"<TerminalBlock title={js('At the PR head: ' + b.get('status', 'not run'))} "
                             f"content={js('$ ' + cmd + chr(10) + b.get('output_tail', ''))} />")
            for k in controls.get(v["id"], []):
                r = k.get("result") or {}
                head = f"Control {k['id']} ({k['recipe']}): {r.get('status', 'not run')}"
                body = k["description"] + "\n" + "\n".join(
                    f"edit {e['op']} {e['path']}" for e in k["edits"]) + "\n\n" + r.get("output_tail", r.get("note", ""))
                parts.append(f"<TerminalBlock title={js(head)} content={js(body)} />")
    return "\n".join(parts)


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
    filled = (template.replace("{{REPO}}", runtime_path(args.runtime))
              .replace("{{TITLE}}", json.dumps(title)).replace("{{SUMMARY}}", json.dumps(summary))
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
