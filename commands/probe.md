# probe

Run each verifier at its commit. Then plant each control (a model-free bug) in its own scratch worktree of a private clone, and record which checks go red. Start it only on an explicit request from the user. The cost is compute only.

## Steps

1. **Check the commands.** Read each `command` and `setup` step in the trust map. Each one must come from the repo's reviewed CI profile and call no model or paid service.
   - **Done when** you can name the CI job for each command.
2. **Probe.** Run `understando probe [--env-file <env.sh>]`. Use `--control K01,K02` or `--only V01` to run a part. The user's checkout and its worktree list do not change.
   - **Done when** it prints the summary. Report each `FLAG` line word for word: a `cannot-fail` verifier is the most important finding of the run.
3. **Fix each error.** An `error` result means that the edit did not apply, or the check failed for another reason. Fix the control's `find` text or its `expect.pattern`, then run that control again.
   - **Done when** no control has an error that you can fix.

A tier on the ladder counts for a claim only after a control shows that its check can fail. See [../references/verdicts.md](../references/verdicts.md).
