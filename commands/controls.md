# controls

Run each verifier at the PR head, then run each control in its own scratch worktree. Start this sub-command only on an explicit request from the user. The default budget is $0: run model-free controls only.

Inputs: `M` from `map`, a git repo that holds the head commit, and, when the verifiers need it, an env file for hermetic runs.

## Steps

1. **Check the inventory.** Run `python3 $U/scripts/validate.py $M`. Read each `command` and each `setup` step. Each one must come from the repo's reviewed CI profile, and it must not call a model or a paid service.
   - **Done when** `VALID` prints, and you can name the CI job for each command.
2. **Isolate the repo.** When the target is the user's own repo, make a local clone for the scratch worktrees: `git clone --shared --no-checkout <repo> <scratch>/clone`. Then the worktree metadata goes into the clone, not into the user's repo.
   - **Done when** `git -C <scratch>/clone cat-file -e <head>` succeeds, or the target is a throwaway repo.
3. **Run the baseline.** Run `python3 $U/scripts/run_control.py --map $M --repo <clone> --baseline --scratch <scratch>/wt [--env-file <env.sh>]`. Each verifier must be green at the head.
   - **Done when** each verifier with a command has a `baseline`. Report each one that is not green, because it backs nothing.
4. **Run the controls.** Run `python3 $U/scripts/run_control.py --map $M --repo <clone> --all --scratch <scratch>/wt [--env-file <env.sh>]`. Each control gets a fresh worktree, the `setup` steps, the edit, the verifier's command and a removal.
   - **Done when** each control has a `result`, and `git -C <clone> worktree list` shows only the clone.
5. **Read each error.** An `error` result means the edit did not apply, or the verifier failed for a different reason. Fix the control's `find` text or its `expect.pattern`, then run that control again with `--control <id>`.
   - **Done when** no control has an `error` that you can fix.
6. **Rate.** Run `python3 $U/scripts/verdicts.py $M`. Report each loud flag word for word. A `cannot-fail` verifier is the most important finding of the run.
   - **Done when** the summary prints and each loud flag is in your report.
7. **Clean up.** Remove the scratch worktree from `map` with `git -C <repo> worktree remove --force <path>`. Remove the clone.
   - **Done when** `git -C <repo> worktree list` no longer lists your scratch paths.

New controls worth keeping, new `@cc` contracts and e2e tests that close a Gap go on a separate branch, as a patch for the author. They never go into the PR's own commits.
