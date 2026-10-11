# probe

Run each verifier at its commit. Then plant each control (a model-free bug) in its own scratch worktree of a private clone, and record which checks go red. Start it only on an explicit request from the user. The cost is compute only.

Each stop of this playbook ends with one question to the user. Ask it as [Asking the user](../references/working-rules.md#asking-the-user) tells you: the situation, a Next line, and numbered options.

## Never paste code

A control names its place with an anchor, not with copied code: `{"op", "path", "symbol", "match"}`, and `"with"` for `replace-with`. The ops are in [../references/controls.md](../references/controls.md). Preview the place with `understando snippet <path>::<symbol> --match TEXT`. The probe resolves the anchor at the commit, in the scratch worktree, and the explainer shows the real diff of that worktree. Typed `find` text costs tokens, and it stops to apply when the code changes.

## Steps

1. **Check the commands.** Each `command` and `setup` step in the trust map must match a command of the approved CI profile (`understando ci`). It must call no model or paid service. probe refuses a command outside the profile. It skips a command that needs the model key, unless the user said yes to its cost (`--paid V36`).
   - **Done when** `understando ci` prints `approved by the user`, and you can name the CI job for each command.
2. **Probe.** Run `understando probe [--env-file <env.sh>]`. Use `--control K01,K02` or `--only V01` to run a part. The user's checkout and its worktree list do not change.
   - **Done when** it prints the summary. Report each `FLAG` line word for word: a `cannot-fail` verifier is the most important finding of the run.
3. **Fix each error.** An `error` result means that the edit did not apply, or the check failed for another reason. An `ANCHOR ERROR` means that the anchor matches 0 places or more than 1. Make the `symbol` or the `match` more precise. Preview it with `understando snippet`, and run that control again. Fix an `expect.pattern` the same way.
   - **Done when** no control has an error that you can fix.

## An e2e test must drive the user path

An e2e verifier must follow the tier-1 proof standards of [../references/controls.md](../references/controls.md#tier-1-proof-standards). It drives the real CLI, service or UI. It captures the action and the state after it, and it checks the side effects. probe reads the test files of each e2e verifier. When a test only calls internal functions, probe prints `FLAG NOT-USER-PATH`, and the kind becomes `integration`. Report the flag. To make the test e2e, drive the real entry point in a subprocess, an HTTP call or a browser.

## The env file

A verifier that needs no model key runs with no env file. Only a paid verifier that the user said yes to (`--paid V36`) gets the key wrapper, for that run only. The flag never stays in the saved trust map. `--env-file` passes the user's own env file to each verifier with `env_file: true`. probe prints a skip line only for a paid verifier in scope (`--only`). `review` shows the paid ones once, as one option with their cost.

## Coverage

Run `understando coverage [--only V14,V15]` after probe. It runs each check with a command one time, at its commit, in a scratch worktree, with a line tracer. It records the changed code files that each check runs in `$R/coverage.json`. The explain step reads this record: a changed file that a check of a claim runs is covered by that claim. The record counts only at the map head. Only commands of the approved CI profile run, and a check that needs the model key does not run. The tracer reads Python only. For other files, a control that edits the file covers it, and a claim that cites the file or names it covers it.

A tier on the ladder counts for a claim only after a control shows that its check can fail. See [../references/verdicts.md](../references/verdicts.md).
