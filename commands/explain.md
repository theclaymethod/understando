# explain

Build the PR-body section and the explainer from `M`. Read [../cards/trust-map.md](../cards/trust-map.md) first. It says what each chapter holds and which visual-explainer cards it reuses.

## Steps

1. **Rate first.** Run `python3 $U/scripts/verdicts.py $M`.
   - **Done when** each claim has a `verdict` and a `reason`.
2. **Write `$R/explain.json`.** Its fields are in the docstring of `scripts/explain.py`. Write about five STE `orientation` sentences and the `architecture` diagram. Write the `tour` in execution order: for each step, text from the PR's own explanation, the code at the head, and the claims that the step protects. Add `diagrams` and `walkthroughs` only where they help understanding, and `control_walkthroughs` for one control that went red and one that a check missed. Rank the `risks`: the weak high-stakes claims first, each with its cheapest fix. Add the trade-offs, the concerns and the verifications of this explainer as short strict-STE sentences. Add at most three `bullets` for the PR-body section.
   - **Done when** each diagram node names a real module or function at the head, each claim shows at a tour step, and each concern cites a claim ID or a file.
3. **Generate.** Run `python3 $U/scripts/explain.py --map $M --repo <repo> --out $R --extra $R/explain.json`. It writes `$R/pr-section.md`, `$R/explainer.mdx` and one MDX file per chapter in `$R/chapters/`. It fails when a claim shows at no tour step.
   - **Done when** both files exist.
4. **Export the HTML.** Run `node <visual-explainer>/scripts/artifacture.mjs export $R/explainer.mdx --out $R/explainer.html`. Fix an export failure in the MDX, not in the HTML.
   - **Done when** `$R/explainer.html` exists.
5. **Check the mechanics.** Run `node <visual-explainer>/scripts/artifacture.mjs verify $R/explainer.html --mechanics-only --json $R/ve-report.json`. The model review pass of visual-explainer is a paid step. Run it only after a yes from the user.
   - **Done when** the report has 0 errors, or you report each error.
6. **Lint the text.** Run `python3 -I <asd-ste100>/scripts/ste-lint.py $R/pr-section.md`. Rewrite each flagged sentence.
   - **Done when** the lint reports 0 hard violations.
7. **Report.** Give the paths of `trust-map.json`, `pr-section.md`, `explainer.mdx` and `explainer.html`. Paste `pr-section.md` into the PR body only when the user asks.
   - **Done when** the user has the paths and the verdict counts.
