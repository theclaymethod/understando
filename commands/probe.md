# probe

Prove that each check of a feature can fail. Start it only on an explicit request from the user. The cost is compute only.

## Controls

`understando probe --feature F` runs each check at its commit, then plants each control in its own scratch worktree of a private clone, and records which checks go red. A control names its place with an anchor, not with copied code: `{"op", "path", "symbol", "match"}` ([../references/controls.md](../references/controls.md)). Preview the place with `understando snippet <path>::<symbol> --match TEXT`.

1. **Run.** `understando probe --feature F` shows the commands; after the user's yes, add `--yes`. `--check V1` or `--control K1` runs a part.
   - **Done when** it prints the strengths. Report each `FLAG` line word for word: a check that cannot fail is the most important finding.
2. **Fix each error.** An `ANCHOR ERROR` means that the anchor matches 0 places or more than 1: make the `symbol` or the `match` more precise, and run that control again.
   - **Done when** no control has an error that you can fix.

## Mutation testing

`understando probe mutate` plants the mutants of a tool and records which tests kill them ([../references/controls.md](../references/controls.md#mutants)).

1. **mutmut, the fast default.** `understando probe mutate --feature F [--paths P] [--tests tests/]`. mutmut runs the tests that its per-test coverage maps to each mutated function. probe then runs each covering test alone against each killed mutant: the kill matrix.
   - **Done when** it prints the summary and each `SURVIVED` line.
2. **cosmic-ray, targeted.** `understando probe mutate --tool cosmic-ray --feature F [--lines PATH:A-B] [--base REF]`. Without `--lines`, it takes the riskiest changed lines: the lines where a mutmut mutant survived, then guards and comparisons. It records the line coverage of each test, runs only the tests that cover the line of a mutant, each one alone.
   - **Done when** each survivor has a test that kills it, or a reason that the user accepted.

The equivalent-mutant filters run before a survivor counts: the same bytecode as the original, the same syntax tree (a docstring or the layout), or a change only in the text of an error, log or print message. The report names the filter of each one. The tools come from the mutation venv (`understando setup --mutation`), or `--venv DIR`.
