# Changelog

## Unreleased: the strip

understando is now verifier-driven development and formal verification, around a project-local verify skill. Everything that served the reviewer of a PR is gone. The tag `pre-strip` (origin/main 4658387) holds the code, the docs and the tests from before; check it out for anything needed back.

Removed:
- The verbs `review`, `open`, `ready`, `close`, `trim`, `publish`, `learn` (the whole `learn/` app), `mode`, `menu`, `signals`, `hook`, `lock`, `ci`, `import`, `note` (and the journal), `map`, `coverage`, `routes`, the aliases `controls` and `rerun`, and copyedit/reword.
- The trust map (`trust-map.json` and its schema), promises, the merge verdict and the blockers (`derive.py`), the ready gates, the promise grouping and the merge lint (`onto.py`, `regroup.py`), the budget, the paid-key wrapper, the orphan review branch, the copy and slogan lints for review prompts (`copy-rules`), the prompt machinery (`prompt.py`), the reviewer feedback rows, the MDX explainer generation (`explain.py`, `example.py`, `cards/`), the stored CI profile, the prompt hook, `commands.json` and the router generator.
- Their docs, the adapted copies that only they used (autoreview, code-review, explain-report, glossary-format, handoff, pr-verification, teach, to-spec, unslop-core), and their tests (`mode-e2e`, `onto-e2e`, `refs-e2e`, `store-e2e`, the old fixture).

Kept and reshaped:
- `create` (new): the verify skill with a feature map and a Verifier section for each feature (surface, bar, verifiers), proven end to end on one feature, after the model of create-verification-skill. Code Contracts is a named backend bar.
- `maintain` (new): the upkeep pass after maintain-verification-skill; it flags a verifier whose control no longer fails.
- `discover`, `build` (the six-step verifier-first loop with a completion criterion for each step), `probe` (controls), `probe mutate` (new: mutmut and cosmic-ray, equivalent-mutant filters, per-test coverage, the kill matrix), `formalize` (Lean, TLA+, the 7-check conformance, receipts, drift, and the new `--recheck`), `snippet`, `export` (new: `trust-map.json` and `refs.resolved.json` for visual-explainer), `doctor` and `setup` (trimmed).
- The evidence store `verify.json` (`schema/verify.schema.json`) replaces the trust map. Strength: a part is as strong as its strongest check that caught its bug; a claim is as strong as its weakest part.
- Salvaged from the stopped ergo work: one check for each formal property, idempotent sync with stable check IDs and names, proposed claims matched by key, fresh control IDs, the `--recheck` flag (now implemented), and the one-line internal-error handler (exit 70, the traceback in a log).
- Commands run only after the user's yes, each time (`--yes`); no approval is stored.
- The test-isolation guard and its self-check.

## Before the strip


- Code refs of the review branch: a check whose verifier has `at` (the ready sha, which reverify_map sets) resolves its test at that commit, and a ref whose file the PR head does not have resolves at the ready head of the map (`coderef.ref_commit`). The PR's own refs keep the PR head. Each ref in refs.resolved.json records its `commit`, and its permalink points there. The page names review-branch code "On the review branch, <path>". `understando snippet` with no `--head` follows the same rule. The #489 build printed "no such file at 3758b0901c" for the formal conformance tests, the L3 regression test and the review checks.
- `commands/explain.md`: the requests chapter quotes only a request that names a claim, and each narrative sentence has 25 words or fewer. The #489 page failed the export on a repeated "no claim" line and on a trade-off sentence of 26 words.
- The derived page text passes the STE gate and the copy rules. The labels "No action:", "Low risk: skim", "It only removes lines" and "Read these first" are now full sentences of 5 words or more. The derived text calls an invariant of the user "accepted", because the STE lint counts the old word as a synonym of "check". A merged claim keeps each source as its own sentence (`regroup.join_sources`). `commands/explain.md` no longer suggests a "Why this matters" aside.
- The test-isolation guard (`scripts/testguard.py`). Each script imports it first. A test run has `UNDERSTANDO_TEST=1` or a Playwright worker marker. In a test run, an audit hook refuses each write outside `UNDERSTANDO_TEST_ROOT`: each open for write, rename, replace, remove, mkdir and rmtree. It also refuses each read of the real `~/.understando`, except in a read-only verb (help, signals, menu, routes, snippet, `mode status`, `lock status` and the `config.py` sub-commands). A refusal stops the process with "understando test guard: ...", and an `except OSError` cannot hide it. The learn app refuses a `my-work` write outside the test root in the same way.
- Out of a test run, `review` refuses a real run folder when the `gh` on PATH is in a temp folder or a test fixture folder. The error names that `gh`.
- `tests/isolate.sh`: each test script sources it first (tests/*.sh, tests/formal/e2e.sh, learn/e2e.sh and learn/web/e2e/*.sh). It sets the guard, the test root and `TMPDIR`. It sets `UNDERSTANDO_HOME` and `UNDERSTANDO_RUNS` under its own `mktemp -d`. Its self-check fails the suite when one of them is in the real `~/.understando`. The Playwright config sets the same variables. `tests/isolate-e2e.sh` plants writes outside the root and a review with a fake `gh`. `tests/e2e.sh` and `learn/e2e.sh` compare the sha256 of the real #489 run files before and after the suite.
- Copy rules (`references/copy-rules.md`, data in `references/copy-rules.json`): the CLI says what happens, once, in the place where it applies. A prompt that holds a reassurance, a slogan, a stock word, a fragment sentence of 4 words or fewer, or a sentence that repeats does not render (`prompt.banned_copy`). `doctor` flags the same phrases in the docs (`copy-banned`). The "Something else" option has the label "Something else" and one fixed line.
- asd-ste100 is required, with no adapted copy: the agent applies it while it writes each text that a reader sees. `scripts/ste.py` runs its lint as a gate on the prompt render, on `map` and `validate.py` (claims, plain text, names, promises), on `discover answer`, on `close` wording, on the PR section and on the README of `publish`. `understando routes` shows it for every verb, and `doctor` flags it when it is missing.
- A claim holds parts, one for each statement, each with its own checks. A part is as strong as its strongest check; a claim is as strong as its weakest part. A check that missed its bug is a flag with an action, not a score. Each TLA+ property is its own check (`regroup.py split_checks`, the `split:` lint).
- Evidence bars for each surface (frontend, backend, llm, other): `references/evidence-bars.md` is their only source. The page, the PR section, the review lines, the ready gate 1, close and publish use them. doctor flags a doc that restates a bar.

- The review ontology: promise -> claim -> check (`scripts/onto.py`). A claim lists its checks (`claims[].checks`, `schema_version` 2), and a merged claim keeps `legacy_ids` and `parts`. A claim is as strong as its weakest check, and its card names that check with its action. `map` writes the new shape, prints the grouping lint (`merge:` and `budget:` lines) and refuses a missing plain name. understando reads the old shape for one release.
- The schema check refuses a claim with no checks, a check that no claim lists, and a claim in more than one promise.
- Plain names: the agent writes the name of each promise, claim and check. doctor flags a cut of the plain text, a path or a tool name.
- `understando coverage` records the changed files that each check runs. A claim covers a file when it cites or names the file. It also covers a file that one of its checks runs or that one of its controls edits.
- The unclaimed level leads with the risky files. Its "what we broke" lines are full sentences.
- `close --add-claim <file>` drafts a claim for a file, attaches the checks that run it, and offers a check. close can fix one weak check of a claim (`fix-check`, `drop-check`).
- `scripts/regroup.py` joins old claims into fewer claims from a proposal, and prints the safety proof.

- understando is a mode with one CLI, `bin/understando`.
- The verbs are map, discover, probe, formalize, import, close, trim, explain, learn (paused), ready, build, setup and doctor. The mode verbs are signals, menu, routes, mode and note.
- The verification ladder (tiers 1 to 5) and the verdict Formal. Proven and Formal need a stated claim or a user-confirmed invariant.
- The intent ledger `journal.jsonl`, the level that tells why the author made each choice, and the ready checklist.
- Adapted copies of pstack and Matt Pocock skill text under `references/adapted/` (MIT, see THIRD_PARTY_NOTICES.md).
- Deprecated: `controls` (now `probe`) and `rerun` (now `map`). Both aliases print the new verb. They go away in the next release.
- The arguments decide: `/understando review 489` runs review, and `/understando 489` is `review 489`. Only a bare invocation shows the menu.
- Each stop ends with one question: at most 5 situation lines, a Next line (scope, cost, time, writes), and at most 4 numbered options. `review`, `menu`, `ci --question` and `close --next` give it as `prompt` in `--json`. `menu --all` adds the verb table.
- review chains its steps into four stops: map + probe on the changed code, close (one claim per question), trim, and ready + explain.
- A possible bug whose code changed on the ready branch asks for a re-check (map + probe), not for discover.
- `ci --approve --project NAME` approves only the commands of one catalog project.
- Run state lives under `~/.understando/runs/<repo>/<pr>/`, never in a git repo. Every verb refuses a run folder inside one, and doctor flags tracked run output. understando's repo no longer tracks `runs/`.
- `publish <pr>` shares a review on the orphan branch `understando/<pr>-review` after a clear yes; `publish --feedback` sends a reviewer's confusion rows back. `fetch_review_branch()` gives `open` a read-only checkout.
- setup pins `ve_runtime` in `~/.understando/config.toml` and prints the PATH line for `~/.local/bin`. java is found from `$JAVA_HOME` or Homebrew's openjdk without a PATH edit.
