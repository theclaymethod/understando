# review

A full PR review from one line: `/understando review <pr>` (Codex: `$understando review <pr>`). `/understando <pr>` is the same. Start it only on an explicit request from the user. The CLI derives the state. Do not ask the user for paths, SHAs, verdict counts or rules: `review` finds them.

Each stop ends with one question to the user. Ask it as [Asking the user](../references/working-rules.md#asking-the-user) tells you. `understando review <pr> --json` gives the question in `prompt`. Its text output is the same question as text. Do not restate the rest of the output.

Run every command in the clone of the reviewed repo, or pass `--repo DIR`.

## Steps

1. **Resolve and ask.** Run `understando review <pr> --json`. It finds the repo from the cwd, owner/repo from `origin`, the PR head from `gh pr view`, the run folder, and the ready branch with its worktree. It makes the worktree from the PR head when it does not exist, and pulls it with `--no-rebase` when it exists. Then it turns the mode on, writes `ci.json`, reads the signals, runs doctor and writes `prompt`.
   - **Done when** you gave the user the `prompt` as text, and the user picked an option.
2. **Do the pick.** Run the `run` command of the picked option. When the CI profile is not approved, the question is the CI approval: "Approve all", "Show the list", or "Approve only <project>" (`understando ci --approve --project <name>`). A pick is the user's yes for that option only.
   - **Done when** the command ends, and it printed the next question.
3. **Stop 1: map + probe on the changed code.** `understando review <pr> --go` runs map, then probe. Probe runs the verifiers that the ready branch changed, the verifiers of a possible bug whose code changed, and the verifiers with no control result. Then formal, only when a formal record covers a changed claim ([formalize.md](formalize.md)). A verifier that needs the model key does not run without a pick that names it (`"paid": ["V36"]` in the answer file). Report each `FLAG` line word for word.
   - **Done when** it printed the close question, or the next stop.
4. **Stop 2: close, one claim per question.** The question names one claim, why it is weak, and the options ([close.md](close.md)). Run `understando discover` before you write a new verifier for a claim that the PR does not state. Put the pick in the answer file as `"close": {"answers": [...]}`, then run `understando review <pr> --go --answers <file>`. It asks about the next claim.
   - **Done when** each open claim has a check that closes it, or has the reason why it stays open.
5. **Stop 3: trim** ([trim.md](trim.md)).
   - **Done when** it printed the trim report, and the user decided each "excess or untested" item.
6. **Stop 4: ready + explain.** It prints the four gates, builds the explainer and prints `pr-section.md`. Give the text to the user to paste. Do not edit the PR description.
   - **Done when** the user has `pr-section.md` and the paths of the explainer.

When the user says "run through", run `understando review <pr> --through`. It does not stop between steps. It still stops for each close choice (claim wording and waivers), the CI approval and each paid step. `discover` (the invariants) stays the user's call.

## Before each hand edit on the ready branch

Before `formalize` or a hand edit changes a file, run `understando review <pr> --guard <path>[,<path>]`. It refuses a secret path and a protected path (report the finding to its owner). It also refuses when origin has commits that the worktree has not pulled, or when a live lock of another writer covers the file. For a long edit, take the lock: `understando lock take --verb formalize --paths ready:<path>`, and release it after the commit.

## The answer file

`{"go": "step" | "run through", "ci": "approve", "ci_project"?: "<name>", "close": {"answers": [...]}, "paid": ["V36"]}`. Write `ci` and `paid` only after the user picked that option in this conversation. The shape of `close` is in `understando close --help`.

## State

`$R/review.json` holds the resolved context, the finished steps and the recorded run time of each step. Run `understando review <pr>` again at any time: it resolves again, pulls the worktree, and asks the next question. `--full` adds the full state.
