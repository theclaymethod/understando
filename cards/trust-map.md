# Trust map card

A visual-explainer card for one PR's trust map. The explainer is teaching material: it gets a developer up to speed on the PR, then shows how strong the verification is. It reuses the visual-explainer runtime, its cards `explain-diff`, `code-walkthrough` and `web-diagram`, and its default components (`Disclosure`, `ChipLinks` and `DiagramModes` among them). It adds no page CSS and no fork. `scripts/explain.py` fills `templates/three-level.mdx` and writes each chapter from `trust-map.json` and `explain.json`. Edit the generated files to tune one PR, then export again.

## The PR-body section

Keep it short. It holds three things and nothing more:

1. One Mermaid diagram: each claim layer, with an edge to each verdict and the count on the edge.
2. The claims-and-verdicts table: claim, verdict and the reason in one strict-STE sentence.
3. Short bullets: the verdict counts, the strength of each promise, each `cannot-fail` verifier, each other loud flag, the control count and cost, and the explainer path.

Put long samples, command output and code in the explainer, not in the PR body. Every code excerpt, diff and permalink comes from a code ref that the build resolves at the head (`scripts/coderef.py`). Nobody types code or a URL: the build stops on pasted code.

## The levels

The explainer is a level ladder for a reader who does not know the code, also a reader outside the team. Each level is one screen deep. Detail waits in a `Disclosure` (a collapsed block). Each level is one self-contained MDX unit in `chapters/NN-<name>.mdx`, with its own imports, so an app can embed it alone. `explainer.mdx` puts each level in a `Section` of an `ExplainerShell` with the chapter rail.

| # | Level | Holds | Visuals |
|---|---|---|---|
| 1 | The story | Three ideas: the problem, the change, and why you can trust it. One chip for each promise, with its weakest verdict. The glossary, collapsed. No code name, no ID and no count beyond the chips. | One before-and-after diagram in two modes. |
| 2 | The loop | The run steps, one plain sentence each, each with a link to its promise. Code excerpts collapsed under each step, copied by the build from the step's code refs, each with its permalink. | The loop diagram in two modes, then the animated walkthrough of one finding. |
| 3 | What changed | A plain intro. A "replaced by" table of deleted code with line counts from `git diff --numstat`. Paths go in the table only. | A before-and-after diagram from the diff, in two modes. Other architecture diagrams, such as the import rules, in two modes. |
| 4 | The promises | One block per promise, weakest first: its sentence, its strength (its weakest claim), a reviewer action when it is weak, and the cheapest fix for each weak claim. Collapsed: its claims, as `plain.what` with a verdict pill. Collapsed under each claim: the proof, the warning, the code, each verifier and each control with its output. | Code and diffs with syntax colours, inside the claim blocks. A control's diff is the real git diff of its scratch worktree, with line numbers. |
| 5 | Verify the verifiers | What red, green and cannot-fail mean. The control count. | The controls animation, labelled from each mutation's own text. The map from each check kind to each claim layer, with every layer, also "Narrative only" and "Unstated changes"; a layer with no check is red. The verifier table, collapsed. |
| 6 | Changed code that no claim covers | Each changed source file that no claim cites, or that is large and mostly uncited, with its line counts and a note on why it matters. | A table; the long tail collapsed. |
| 7 | Trade-offs and concerns | The trade-offs, the concerns, and the verifications of the explainer itself. | None. |
| 8 | Exercises | A placeholder. The learning app fills it. | None. |

Each claim's sentence (`plain.what`) shows once, in its claim block. Other places link to the block, and a link opens each block around it.

## Diagram modes

Each architecture diagram is a `DiagramModes` with a Simple (ELI5) and a Detailed mode, and one labelled switch that the whole page shares and remembers. The Simple mode has about four to six plain boxes and plain-verb edges. The Detailed mode keeps the same node ids, so each box keeps its place, names each box by its real module or function, and adds a few boxes at most. The controls animation and the verifier map stay in one mode.

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
