# Trust map card

A visual-explainer card for one PR's trust map. The explainer is teaching material: it gets a developer up to speed on the PR, then shows how strong the verification is. It reuses the visual-explainer runtime and its cards `explain-diff`, `code-walkthrough` and `web-diagram`. It adds no component and no fork. `scripts/explain.py` fills `templates/three-level.mdx` and writes each chapter from `trust-map.json` and `explain.json`. Edit the generated files to tune one PR, then export again.

## The PR-body section

Keep it short. It holds three things and nothing more:

1. One Mermaid diagram: each claim layer, with an edge to each verdict and the count on the edge.
2. The claims-and-verdicts table: claim, verdict and the reason in one strict-STE sentence.
3. Short bullets: the verdict counts, each `cannot-fail` verifier, each other loud flag, the control count and cost, and the explainer path.

Put long samples, command output and code in the explainer, not in the PR body.

## The chapters

Each chapter is one self-contained MDX unit in `chapters/NN-<name>.mdx`, with its own imports, so an app can embed it alone. `explainer.mdx` puts each chapter in a `Section` of an `ExplainerShell` with the chapter rail.

| # | Chapter | Holds | Visuals |
|---|---|---|---|
| 1 | Orientation | About five STE sentences: what the PR does and why. The glossary. | One static architecture diagram. |
| 2 | Guided tour | The code path in execution order, with the PR body's "How it works" text and the code at the head. At each step, the claims that protect it: `plain.what` and a verdict chip. Each claim shows at a step at least once; `explain.py` fails when one does not. | Static diagrams where they help, for example the import boundary. One animated walkthrough of a finding through the loop. |
| 3 | Confidence | The claims ranked by risk, not by count: the weak high-stakes claims first, each with the cheapest fix. Then a short "what is solid" summary and the verifier map. | One animated walkthrough of controls: a planted bug and the check that turns red, and a pin that stays green while a wider check turns red. A static map from verifier kinds to claim layers. |
| 4 | Evidence | A claim index, then per claim: the plain text (what it is, how it is proven, a warning), the code, each verifier, and each control with its edit as a diff and its output. | Code and diffs with syntax colours. |
| 5 | Trade-offs and concerns | The trade-offs, the concerns, and the verifications of the explainer itself. | None. |
| 6 | Exercises | A placeholder. The learning app fills it. | None. |

## One colour key

- **Verdict:** Proven, Backed, Asserted and Gap use visual-explainer's `ok`, `info`, `warn` and `err` tones. Each pill, node and key entry also shows the word.
- **Tier:** a fact-tier verifier has a solid outline. A guess-tier verifier has a dashed, hatched outline.
- **Verifier kind:** a glyph, not a colour: a rectangle for a static check, an oval for a run check, a diamond for a model judge.
- **Control result:** `caught` (the check went red) uses the `ok` tone. `missed` (the check stayed green) uses the `warn` tone.

Each diagram has a key that lists only the encodings it uses.

## Rules

- A verdict in the explainer comes from `verdicts.py`, never from your own judgement. Show the `reason` with it.
- Each diagram node names a module or a function that exists at the head. Each edge label says what the direction alone cannot say. A node label that names claim IDs takes the colour of their weakest verdict.
- Use animation only where motion carries meaning: an ordered handoff, or a control from the planted bug to the result. `DiagramWalkthrough` starts paused and keeps manual steps under reduced motion.
- Show a control's output tail as evidence. A table cell that says "red" without the output is a claim, not evidence.
- Put each value into MDX as a JSX string expression, as `explain.py` does, so a brace in a claim does not break the parse.
- Keep figure labels at 14px or more. Split a diagram before you make its type smaller.
