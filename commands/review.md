# review

A full PR review from one line: `/understando review <pr>` (Codex: `$understando review <pr>`). Start it only on an explicit request from the user. The CLI derives the state. Do not ask the user for paths, SHAs, verdict counts or rules: `review` finds them.

Run every command in the clone of the reviewed repo, or pass `--repo DIR`.

## Steps

1. **Resolve and set up.** Run `understando review <pr>`. It finds the repo from the cwd, owner/repo from `origin`, the PR head from `gh pr view`, the run folder, and the ready branch with its worktree. It makes the worktree from the PR head when it does not exist, and pulls it with `--no-rebase` when it exists. Then it turns the mode on, writes `ci.json`, reads the signals and runs doctor.
   - **Done when** it prints `STOP: wait for the user's go`.
2. **Show the state.** Give the user the summary as it prints. It shows the verdict counts, each open Gap and Asserted claim, and each deferred invariant with its owner. It also shows each Formal (pending) item, the claims that the ready branch can verify again, and the gates. When the CI profile is not approved, show `understando ci` to the user. Only the user approves it: `understando ci --approve`.
   - **Done when** the user said go, or "run through", or stop.
3. **map.** On a go, run `understando review <pr> --go`. It points the verifiers of each claim that the ready branch changed at the ready tip, then runs `map`. When no trust map exists, write the claim ledger first ([map.md](map.md)).
   - **Done when** it prints the map summary and `STOP: map is done`.
4. **probe.** On a go, run `understando review <pr> --go`. It runs only commands of the approved CI profile. A command that needs the model key does not run: show its cost, and pass `"paid": ["V36"]` in the answer file only after a clear yes.
   - **Done when** it prints the probe summary. Report each `FLAG` line word for word.
5. **formal.** This step runs only when a formal record covers a claim that the ready branch changed. It runs the formal commands of `ci.json` at the ready tip. Then re-run the frog scripts of `$R/formal/`, stamp each record again, and ask the user to start `understando formalize --sidecar $R/formal/verifiers.json` ([formalize.md](formalize.md)).
   - **Done when** each formal command is green, or you reported each red one with its output.
6. **close.** Close each open claim with the user, riskiest first, one claim at a time ([close.md](close.md)). Run `understando discover` before you write a new verifier for a claim that the PR does not state. Put the user's choices in the answer file as `"close": {"answers": [...]}`, then run `understando review <pr> --go --answers <file>`.
   - **Done when** it prints `DONE`, or each open claim has the reason why it stays open.
7. **trim.** On a go, run `understando review <pr> --go` ([trim.md](trim.md)).
   - **Done when** it prints the trim report, and the user decided each "excess or untested" item.
8. **ready --report.** On a go, run `understando review <pr> --go`. It prints the four gates.
   - **Done when** the four gate lines print.
9. **explain.** On a go, run `understando review <pr> --go`. It builds the explainer and prints `pr-section.md`. Give the text to the user to paste. Do not edit the PR description.
   - **Done when** the user has `pr-section.md` and the paths of the explainer.

When the user says "run through", run `understando review <pr> --through`. It runs each remaining step. It still stops for close choices, the CI approval and paid steps.

## Before each hand edit on the ready branch

Before `formalize` or a hand edit changes a file, run `understando review <pr> --guard <path>[,<path>]`. It refuses a secret path and a protected path (report the finding to its owner). It also refuses when origin has commits that the worktree has not pulled, or when a live lock of another writer covers the file. For a long edit, take the lock: `understando lock take --verb formalize --paths ready:<path>`, and release it after the commit.

## The answer file

`{"go": "step" | "run through", "ci": "approve", "close": {"answers": [...]}, "paid": ["V36"]}`. Write `ci` and `paid` only after a clear yes from the user in this conversation. The shape of `close` is in `understando close --help`.

## State

`$R/review.json` holds the resolved context and the finished steps. Run `understando review <pr>` again at any time: it resolves again, pulls the worktree, and prints the summary and the next step.
