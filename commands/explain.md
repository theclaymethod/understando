# explain

Build the PR-body section and the three-level explainer from `M`. Read [../cards/trust-map.md](../cards/trust-map.md) first. It says what each level holds and which visual-explainer cards it reuses.

## Steps

1. **Rate first.** Run `python3 $U/scripts/verdicts.py $M`.
   - **Done when** each claim has a `verdict` and a `reason`.
2. **Write `$R/explain.json`.** Add the architecture diagram and the code-path diagram as DiagramCanvas nodes and edges, taken from the code at the head. Add the trade-offs, the concerns and the verifications of this explainer as short strict-STE sentences. Add at most three `bullets` for the PR-body section.
   - **Done when** each diagram node names a real module or function at the head, and each concern cites a claim ID or a file.
3. **Generate.** Run `python3 $U/scripts/explain.py --map $M --repo <repo> --out $R --extra $R/explain.json`. It writes `$R/pr-section.md` and `$R/explainer.mdx`.
   - **Done when** both files exist.
4. **Export the HTML.** Run `node <visual-explainer>/scripts/artifacture.mjs export $R/explainer.mdx --out $R/explainer.html`. Fix an export failure in the MDX, not in the HTML.
   - **Done when** `$R/explainer.html` exists.
5. **Check the mechanics.** Run `node <visual-explainer>/scripts/artifacture.mjs verify $R/explainer.html --mechanics-only --json $R/ve-report.json`. The model review pass of visual-explainer is a paid step. Run it only after a yes from the user.
   - **Done when** the report has 0 errors, or you report each error.
6. **Lint the text.** Run `python3 -I <asd-ste100>/scripts/ste-lint.py $R/pr-section.md`. Rewrite each flagged sentence.
   - **Done when** the lint reports 0 hard violations.
7. **Report.** Give the paths of `trust-map.json`, `pr-section.md`, `explainer.mdx` and `explainer.html`. Paste `pr-section.md` into the PR body only when the user asks.
   - **Done when** the user has the paths and the verdict counts.
