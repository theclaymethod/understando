# Trust map card

A visual-explainer card for one PR's trust map. It reuses the visual-explainer runtime and three of its cards: `explain-diff`, `code-walkthrough` and `web-diagram`. It adds no component and no fork. `scripts/explain.py` fills `templates/three-level.mdx` from `trust-map.json` and `explain.json`. Edit the generated `explainer.mdx` to tune one PR, then export it again.

## The PR-body section

Keep it short. It holds three things and nothing more:

1. One Mermaid diagram: each claim layer, with an edge to each verdict and the count on the edge.
2. The claims-and-verdicts table: claim, verdict and the reason in one strict-STE sentence.
3. Short bullets: the verdict counts, each `cannot-fail` verifier, each other loud flag, the control count and cost, and the explainer path.

Put long samples, command output and code in the explainer, not in the PR body.

## The three levels

| Level | Holds | Components | Card it reuses |
|---|---|---|---|
| High | Every claim with its verdict on one screen, and a callout for each loud flag. | an HTML table, `Callout` | none |
| Medium | The architecture diagram, the code-path diagram, the claims-by-verdict diagram, and the map from each verifier to its claims and controls. | `DiagramCanvas`, an HTML table | `web-diagram` |
| Low | Per claim: the code at the head. Per verifier: the command and its output at the head. Per control: the edit and the result. | `CodeBlock`, `TerminalBlock` | `code-walkthrough`, `explain-diff` |

Then three meta sections: trade-offs, concerns, and the verifications of the explainer itself.

## Rules

- A verdict in the explainer comes from `verdicts.py`, never from your own judgement. Show the `reason` with it.
- Each diagram node names a module or a function that exists at the head. Each edge label says what the direction alone cannot say.
- Show a control's output tail as evidence. A table cell that says "red" without the output is a claim, not evidence.
- Put each value into MDX as a JSX string expression, as `explain.py` does, so a brace in a claim does not break the parse.
- Keep figure labels at 14px or more. Split a diagram before you make its type smaller.
