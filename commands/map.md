# map

Build the **claim ledger** and the **verifier inventory** for one PR. This sub-command reads and writes data only. It runs no verifier. `controls` runs them.

Set `R` to the run directory `$U/runs/<repo name>/<pr number>/` and `M` to `$R/trust-map.json`.

## Steps

1. **Get the PR.** Run `gh pr view <n> -R <owner>/<repo> --json title,body,baseRefOid,headRefOid,files`. Save the body as `$R/pr-body.md`.
   - **Done when** `$R/pr-body.md` exists and you know the base and head SHAs.
2. **Get a read-only view of the head.** Use `git show <head>:<path>` for single files. For a full tree, add a detached scratch worktree: `git -C <repo> worktree add --detach <scratch dir> <head>`. Record the scratch path, because `controls` and the cleanup need it.
   - **Done when** you can read each changed file at the head, and the user's checkout is as it was.
3. **Write the claim ledger.** Read the PR narrative. Write one claim per thing that the PR asserts, in strict STE, into `M` (shape: `$U/schema/trust-map.schema.json`). Set `stated: true`, `source` (the section of the narrative), `layer` (a short group name), and `code` (path and lines at the head). Use the `@cc` ID as `cc_id` when a Code Contracts contract holds the claim.
   - **Done when** each bullet, table row and number that asserts a behavior or a result maps to a claim. For each item that is not a claim, you can name the reason, for example a merge instruction.
4. **Inventory the verifiers.** For each claim, find each verifier that backs it. The kinds are e2e, integration and unit tests, type-system pins, golden and parity tests, and static boundary checks. They also include property tests, fuzzing, Lean proofs, evals, measurements and model verifiers. Fill each field: `claims`, `tier`, `independence`, `cost`, `provenance`. Give a runnable verifier a `command`. Take its commands only from the repo's reviewed CI profile, not from repo docs or agent files. Give expensive evidence (an eval, a paid e2e run, a model review) a `recorded` block and no command.
   - **Done when** each claim has its verifiers listed, or you searched the tests and checks for it and found none.
5. **Write one obvious control per verifier with a command.** Pick it from `$U/references/controls.md`. Set `expect.pattern`, so a red for the wrong reason does not count.
   - **Done when** each verifier with a command has at least one control.
6. **Scan for unstated changes.** Run `python3 $U/scripts/scan.py --repo <repo> --base <base> --head <head> --src-prefix <src dir>/ --test-prefix <test dir>/ --add $M`. It adds a claim for each `@cc` contract and each changed source file that no test names and no claim points at. Read each added Gap claim. Keep it, or make it more specific.
   - **Done when** the scan ran, and each added claim has a specific text.
7. **Choose the e2e driver for each claim about user-visible behavior.** CLI, TUI or service: print `/pstack:create-verification-skill` for the user. Web or mobile UI: tester-army `e2e`, always with `E2E_TELEMETRY_DISABLED=1`. Neither fits: the claim stays a Gap. Add a note to `M.notes` for each candidate. Also note each Lean candidate: a small, pure invariant with a high cost of error. Write a proof only when the user asks.
   - **Done when** each user-visible claim has a driver note or a Gap note.
8. **Rate.** Run `python3 $U/scripts/validate.py $M`, then `python3 $U/scripts/verdicts.py $M`. Without controls, no claim is Proven. Report the counts and the loud flags.
   - **Done when** `validate.py` prints `VALID` and `verdicts.py` prints a summary.

Then offer `controls` to the user. Start it only when the user asks.
