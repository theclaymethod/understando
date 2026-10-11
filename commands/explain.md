# explain

Build the explainer and the PR-body section from `M`. Read [../cards/trust-map.md](../cards/trust-map.md), then the visual-explainer card **`trust-map`** (`<visual-explainer>/cards/trust-map.md`). That card holds the data contract, the components and the export checks.

Each stop of this playbook ends with one question to the user. Ask it as [Asking the user](../references/working-rules.md#asking-the-user) tells you: the situation, a Next line, and numbered options.

The explainer is a **guided review**: ten chapters, one page each, that take a reviewer from what the PR does to the merge call. With JavaScript, the page shows one chapter at a time, with previous and next links and "Read as one page". Without JavaScript, each chapter shows in sequence. Detail waits in collapsed blocks: a newcomer meets the big picture first, and an ID or a code name only when they open a block.

## Content rules

The content rules of explain-report hold for each level ([../references/adapted/explain-report.md](../references/adapted/explain-report.md)). Lead with the decision: can the reviewer merge? Give evidence for each claim. Keep verified, inferred and unknown apart. Put depth behind a collapsed block. The pipeline stays the same: MDX from the trust map, exported by the visual-explainer runtime. `understando explain --html` runs the build and the export.

## Never paste code

Do not type code, line numbers or a GitHub URL into `explain.json`, the trust map or `explainer.mdx`. Write a code ref: `{"path", "symbol"}`, with `"match"` and `"context"` for a part of a symbol; in the MDX, a `<CodeRef refs={refs} path="..." symbol="..." />`. Preview it with `understando snippet <path>::<symbol>`. The build copies the lines at the head and makes each permalink from the git remote and the head SHA. A ref resolves again at each head.

## Steps

1. **Rate first.** Run `understando map`.
   - **Done when** each claim has a `verdict` and a `reason`, and each promise in `M` has its claims.
2. **Write `$R/explain.json`: the data.** Write all text in strict STE.
   - **`diagrams`:** each architecture diagram in two modes. **ELI5 (Simple, the default):** about four to six boxes in plain words and plain-verb edges, no code name and no ID. **Detailed:** the same node ids, each named by its real module or function at the head, 1.5 times the ELI5 boxes or fewer.
   - **`walkthroughs`:** the animated loop, with plain labels.
   - **`change.areas`:** the areas of the diff: each a plain `name`, its path prefixes, and `replaced_by` (an area id) or a `note` for deleted code. Mark a large package `rollup`. The page takes every line count from the diff, so write no count by hand.
   - **`change.chapters`:** the chapters of the change, in reading order. Each one is one idea, titled as a plain action ("Gate every finding before the editor sees it"), never a file name. Give each a `tier` (`core`, `supporting`, `wiring`, `data`, `docs` or `generated`), one or two `explain` paragraphs of 25 to 60 words (what happens at run time, and why; do not restate the diff), and its `files` (paths or path prefixes, in reading order). Put each changed file that is not a test in exactly one chapter. A file in none shows in a chapter "Files that no chapter holds", with an action. Do not make a chapter of the tests: the page shows each test as the checks that it provides.
   - **Typed diagrams:** in `diagrams`, a `sequence` (who calls whom: at most 5 actors and 12 messages), a `state` (a lifecycle: each transition has a label), a `schema` (data shapes) or a `flow`, when a picture explains faster than prose. Mark each element `added`, `changed`, `removed` or `same`, give it a `code` name for the Detailed mode, and a `chapter` to link to. Name the diagram in its chapter's `diagrams`. Draw only what the code does.
   - **`verdict.checks`:** the checks to finish before approval. Each one is a thing to do: `check` (a verifier id; the page shows its command), `run` (a command), `ref` (the lines to read), `file` (a file to compare) or `inputs` (real inputs for a manual test). No general advice.
   - **`unclaimed`:** `notes` (why a risky file matters), `roles` (its job in plain words, for example "cost metering") and `core` (the path prefixes of the core harness files).
   - **`risks`:** the cheapest fix for each weak claim. **`control_walkthroughs`:** the example of a planted bug. **`bullets`:** at most three, for the PR body.
   - **Layout hints:** `"modes": "independent"` on an architecture diagram lays out its Simple and Detailed modes each on its own grid, so the Simple mode has no empty space. `"direction": "horizontal"` or `"vertical"` sets its direction.
   - **Done when** each Detailed node names a real module or function at the head, and each changed file that is not a test is in one chapter.
3. **Write `$R/explainer.mdx`: the narrative.** Markdown in strict STE, as the visual-explainer card `trust-map` shows. Use `<ExplainerShell ... paged>` and one `Section` for each chapter, with the ids and the aliases of the card:
   - `ch-0` **Start:** a `<Lead>` of about three plain lines (what the PR does), then `<ReviewStart>`: the merge state, the progress and the three riskiest items.
   - `ch-1` **The problem and the change:** a `DefinitionList` (before, after, the main risk) and the story diagram. Put the user's requests from the journal, each a quote with its claims, in a `Disclosure`.
   - `ch-2` **How it works:** a `<StepThrough>` around `<ArchitectureDiagram ... numbered />` and its `Steps`: one finding (or one request) through the loop, five or six steps, each with its promise and its code as a `CodeRef`. The numbered boxes match the numbered steps.
   - `ch-3` **What changed:** `<DiffSpine>`. `ch-4` **Reading the evidence:** `<EvidenceGuide>`. `ch-5` **The checks:** `<VerifierView>`. `ch-6` **Check yourself:** `<UnderstandingCheck>`. `ch-7` **The review:** `<ReviewChecklist>`. `ch-8` **The verdict:** `<ReviewVerdict>`, `<ApproveChecks>`, the trade-offs, concerns and verifications in Markdown, then `<Glossary only="used">`. `ch-9` **Every changed file:** `<FullDiff>`.
   - **The reading path:** title each chapter with the one question that it answers, for example "How does one finding move through the loop?". Open a chapter with a `<Lead>` when it helps: its answer in plain words, in one or two sentences. Put a second figure, such as the import rules, in a `Disclosure`. Use an `<Aside>` ("Why this matters") only for a fact that changes how the reader judges the PR, in two sentences at most. Write no CSS: the components set the type and the spacing.
   - **The identifier rule:** an ID or a backticked code name shows only in a table, in a collapsed block, in a `CodeRef`, in a data component or in the Detailed mode of a diagram. The export fails on any other one.
   - **Done when** each chapter of the card is a `Section` with its id.
4. **Generate.** Run `understando explain`. It checks the data (the map, the mechanical checks again, pasted code in the data), resolves the code refs and the control patches into `$R/refs.resolved.json`, and exports `$R/explainer.html` through visual-explainer: a static pre-render that validates the data and runs the export checks, with the no-hand-copy guard for the MDX. It writes `$R/pr-section.md`, `$R/GLOSSARY.md` and `$R/explain.stamp.json` (the map head and the hashes of the trust map, the MDX and `pr-section.md`); `understando publish` refuses an explainer that does not match the stamp. It passes `ve_runtime` from `~/.understando/config.toml` as `--runtime`.
   - **Done when** it prints the promise strengths. Fix a failure in the MDX or the data, not in the HTML.
5. **Check the mechanics.** Run `node <visual-explainer>/scripts/artifacture.mjs verify $R/explainer.html --mechanics-only --json $R/ve-report.json`. The model review pass of visual-explainer is a paid step. Run it only after a yes from the user.
   - **Done when** the report has 0 errors, or you report each error.
6. **Lint the text.** Run `python3 -I <asd-ste100>/scripts/ste-lint.py $R/pr-section.md`, and lint the narrative of `explainer.mdx` and the strings of `explain.json` the same way. Rewrite each flagged sentence.
   - **Done when** the lint reports 0 hard violations.
7. **Report.** Give the paths of `trust-map.json`, `pr-section.md`, `explainer.mdx` and `explainer.html`. Paste `pr-section.md` into the PR body only when the user asks.
   - **Done when** the user has the paths, the verdict counts and the promise strengths.
