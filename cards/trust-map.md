# Trust map card

The explainer of a PR's trust map is a visual-explainer page. Its card is **`trust-map`** in the visual-explainer skill (`<visual-explainer>/cards/trust-map.md`). Read that card before you write the explainer: it holds the data contract, the stable anchors, the components and the export checks.

The page follows the review ontology: promise, then claim, then check (`commands/map.md`). Each promise card shows its claim count. Each claim card shows "N checks: x caught their bug, y missed", then its weakest check in plain words, with its action. The checks of a claim stay collapsed. "Can these checks catch a bug?" counts checks, not planted bugs. `scripts/derive.py` derives each of these values. The components only show them.

A role is a plain phrase for the job of a file, for example "the UAP adapter" or "the CLI and its exit codes".

understando's part is small:

- **The data.** `trust-map.json` (the map step, the controls and the verdicts) and `explain.json` (the explain step: the diagrams, the change areas, the unclaimed notes and roles, the risks, the control walkthroughs and the PR-body bullets). Both in strict STE.
- **The narrative.** `explainer.mdx` in the run folder, written by the explain step: Markdown for the story, why it was built this way, the loop and the trade-offs, with the data components of the card dropped in (`MergeVerdict`, `PromiseList`, `VerifyTheVerifiers`, `UnclaimedChanges` and the others).
- **The glue.** `understando explain` (`scripts/explain.py`) checks the data, resolves each code ref (each claim ref and each `<CodeRef>` of the MDX) and each control patch at the head into `refs.resolved.json`, runs the visual-explainer export with the no-hand-copy guard, writes `pr-section.md` through the same rules as the page, and stamps the build (`explain.stamp.json`).

## The PR-body section

Keep it short: the merge verdict, the ready checklist when `ready.json` is at the map head, one Mermaid diagram (each claim layer, an edge to each verdict, the count on the edge), the claims-and-verdicts table, and short bullets (the verdict counts, the strength of each promise, each `cannot-fail` verifier, each other loud flag, the control count and cost, the explainer path). Put long samples, output and code in the explainer, not in the PR body.

## Rules

- A verdict in the explainer comes from `verdicts.py`, never from your own judgement.
- Every code excerpt, diff and permalink comes from a code ref that the build resolves at the head. Nobody types code or a URL.
- Each diagram node in the Detailed mode names a module or a function that exists at the head.
