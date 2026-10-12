# Changelog

## Unreleased: the strip

understando is now verifier-driven development and formal verification, around a project-local verify skill. Everything that served the reviewer of a PR is gone. The tag `pre-strip` (origin/main 4658387) holds the code, the docs and the tests from before; check it out for anything needed back.

Removed:
- The verbs `review`, `open`, `ready`, `close`, `trim`, `publish`, `learn` (the whole `learn/` app), `mode`, `menu`, `signals`, `hook`, `lock`, `ci`, `import`, `note` (and the journal), `map`, `coverage`, `routes`, the aliases `controls` and `rerun`, and copyedit/reword.
- The review trust map as the store of a run, and its schema (`export` now writes `trust-map.json` from `verify.json`, for visual-explainer), promises, the merge verdict and the blockers (the old `derive.py`; the new one words the export), the ready gates, the promise grouping and the merge lint (`onto.py`, `regroup.py`), the budget, the paid-key wrapper, the orphan review branch, the copy and slogan lints for review prompts (`copy-rules`), the prompt machinery (`prompt.py`), the reviewer feedback rows, the MDX explainer generation (`explain.py`, `example.py`, `cards/`), the stored CI profile, the prompt hook, `commands.json` and the router generator.
- Their docs, the adapted copies that only they used (autoreview, code-review, explain-report, glossary-format, handoff, pr-verification, teach, to-spec, unslop-core), and their tests (`mode-e2e`, `onto-e2e`, `refs-e2e`, `store-e2e`, the old fixture).

Kept and reshaped:
- `create` (new): the verify skill with a feature map and a Verifier section for each feature (surface, bar, verifiers), proven end to end on one feature, after the model of create-verification-skill. Code Contracts is a named backend bar.
- `maintain` (new): the upkeep pass after maintain-verification-skill; it flags a verifier whose control no longer fails.
- `discover`, `build` (the six-step verifier-first loop with a completion criterion for each step), `probe` (controls), `probe mutate` (new: mutmut and cosmic-ray, equivalent-mutant filters, per-test coverage, the kill matrix), `formalize` (Lean, TLA+, the 7-check conformance, receipts, drift, and the new `--recheck`), `snippet`, `export` (new: `trust-map.json` and `refs.resolved.json` for visual-explainer), `doctor` and `setup` (trimmed).
- The evidence store `verify.json` (`schema/verify.schema.json`) replaces the trust map as the store of a run. Strength: a part is as strong as its strongest check that caught its bug; a claim is as strong as its weakest part.
- Salvaged from the stopped ergo work: one check for each formal property, idempotent sync with stable check IDs and names, proposed claims matched by key, fresh control IDs, the `--recheck` flag (now implemented), and the one-line internal-error handler (exit 70, the traceback in a log).
- Commands run only after the user's yes, each time (`--yes`); no approval is stored.
- The test-isolation guard and its self-check.

## Before the strip

The history of the review tool is in the tag `pre-strip` (origin/main 4658387): run `git show pre-strip:CHANGELOG.md`.
