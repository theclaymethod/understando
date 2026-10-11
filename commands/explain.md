# explain

Build the PR-body section and the explainer from `M`. Read [../cards/trust-map.md](../cards/trust-map.md) first. It says what each level holds and which components it uses.

Each stop of this playbook ends with one question to the user. Ask it as [Asking the user](../references/working-rules.md#asking-the-user) tells you: the situation, a Next line, and numbered options.

The explainer is a **level ladder**. Each level is one screen deep, and detail waits in collapsed blocks. A newcomer meets the big picture first and an ID or a code name only when they open a block.

## Content rules

The content rules of explain-report hold for each level ([../references/adapted/explain-report.md](../references/adapted/explain-report.md)). Lead with the decision: can the reviewer merge? Give evidence for each claim. Keep verified, inferred and unknown apart. Put depth behind a collapsed block. The pipeline stays the same: MDX from the trust map, exported by the visual-explainer runtime. `understando explain --html` runs the build and the export.

## Never paste code

Do not type code, line numbers or a GitHub URL into `explain.json` or into the trust map. Write a code ref: `{"path", "symbol"}`, with `"match"` and `"context"` for a part of a symbol. Preview it with `understando snippet <path>::<symbol>`. The build copies the lines at the head, and it makes each permalink from the git remote and the head SHA. Typed code costs tokens to read and to write again, and it does not change when the code changes. A ref resolves again at each head.

## Steps

1. **Rate first.** Run `understando map`.
   - **Done when** each claim has a `verdict` and a `reason`, and each promise in `M` has its claims.
2. **Write `$R/explain.json`.** Its fields are in the docstring of `scripts/explain.py`. Write all text in strict STE.
   - **`story`:** three ideas, one sentence or two each: the problem, the change, and why the reader can trust it. No code name, no ID and no count. Name the before-and-after picture in `picture`.
   - **`loop`:** the run steps in execution order, one plain sentence each, each with the `promise` that protects it. Put code refs (not code) in a step's `code`; the build copies the lines, and the page collapses them. Add a `walkthrough` (the animated loop) with plain labels.
   - **`change`:** the `areas` of the diff: each a plain `name`, its path prefixes, and `replaced_by` (an area id) or a `note` for deleted code. Mark a large package `rollup` to show it as one row. `explain.py` takes every line count from `git diff --numstat`, so write no count by hand.
   - **`unclaimed.notes`:** one plain line on why a risky unclaimed file matters, for example the exit codes.
   - **`risks`:** the cheapest fix for each weak claim. The promises level shows it.
   - Trade-offs, concerns and the verifications of this explainer, as short strict-STE sentences. At most three `bullets` for the PR-body section.
   - **Done when** each diagram node names a real module or function at the head (Detailed mode), each loop step names a promise, and each concern cites a claim ID or a file.
3. **Draw each architecture diagram in two modes.** In `diagrams`, give each one an `eli5` and a `detailed` node and edge set.
   - **ELI5 (Simple, the default):** about four to six boxes in plain words, for example "The finished CR", "Make a draft", "Check it", "Repair it", "Keep or undo", "Release or block". Edge labels are plain verbs. No code name and no ID.
   - **Detailed:** the same node ids, each named by its real module or function at the head, for example `load_finished_cr` or `Editor.edit`. Add a few nodes at most: 1.5 times the ELI5 count or fewer.
   - **The identifier rule for levels 1 to 3:** an identifier (a code name or an ID) is visible only in the Detailed mode of a diagram, in a table, or in a collapsed block. `explain.py` fails on any other one.
   - **Done when** each diagram that `story.picture`, `loop.diagram` or `change.diagrams` names has both modes, and the Detailed mode matches the code at the head.
4. **Generate.** Run `understando explain`. It runs `scripts/explain.py` with `$R/explain.json`, the journal and `ready.json`. The journal gives the level that tells why the author made each choice. `ready.json` gives the checklist at the top. It also writes `$R/GLOSSARY.md`. It writes `$R/pr-section.md`, `$R/explainer.mdx` and one MDX file per level in `$R/chapters/`. It fails when an identifier shows in levels 1 to 3 outside the places that step 3 allows, when a diagram lacks a mode, when a claim has no single block or a link has no target, when a weak promise has no reviewer action, when the page uses a term that the glossary does not define, when a mechanical check gives a new result, when a code ref resolves to no place or to more than one, or when an input holds pasted code (two or more lines that are the same as a file at the head). It writes the resolved lines to `$R/refs.resolved.json`, not into the data. It passes `ve_runtime` from `~/.understando/config.toml` as `--runtime`, and after a good build it writes `$R/explain.stamp.json` (the map head and the hashes of the trust map, the MDX and `pr-section.md`); `understando publish` refuses an explainer that does not match it.
   - **Done when** it prints the glossary size and the promise strengths. Fix a failure in the data, not in the generated files.
5. **Export the HTML.** Run `node <visual-explainer>/scripts/artifacture.mjs export $R/explainer.mdx --out $R/explainer.html`. Fix an export failure in the MDX, not in the HTML.
   - **Done when** `$R/explainer.html` exists.
6. **Check the mechanics.** Run `node <visual-explainer>/scripts/artifacture.mjs verify $R/explainer.html --mechanics-only --json $R/ve-report.json`. The model review pass of visual-explainer is a paid step. Run it only after a yes from the user.
   - **Done when** the report has 0 errors, or you report each error.
7. **Lint the text.** Run `python3 -I <asd-ste100>/scripts/ste-lint.py $R/pr-section.md`, and lint the strings of `explain.json` the same way. Rewrite each flagged sentence.
   - **Done when** the lint reports 0 hard violations.
8. **Report.** Give the paths of `trust-map.json`, `pr-section.md`, `explainer.mdx` and `explainer.html`. Paste `pr-section.md` into the PR body only when the user asks.
   - **Done when** the user has the paths, the verdict counts and the promise strengths.
