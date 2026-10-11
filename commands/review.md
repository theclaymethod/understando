# review

For the author: a full PR review from one line, `/understando review <pr>` (Codex: `$understando review <pr>`). `/understando <pr>` is the same. Start it only on an explicit request from the user. The CLI derives the state. Do not ask the user for paths, SHAs, verdict counts or rules: `review` finds them.

The situation lines and the progress lines use the words of the evidence bars ([evidence-bars.md](../references/evidence-bars.md)).

Each stop ends with one question. Ask it as [Asking the user](../references/working-rules.md#asking-the-user) tells you. `understando review <pr> --json` gives the question in `prompt`, and the text output is the same question. Do not restate the rest of the output. Use plain names in chat ([Reporting](../references/working-rules.md#reporting)).

Run every command in the clone of the reviewed repo, or pass `--repo DIR`. The run folder is under `config.runs_root()` (`~/.understando/runs/<repo>/<pr>/`), never in a git repo.

## The first stop

`understando review <pr> --json` resolves the repo, the PR head (`gh pr view`), the run folder and the ready worktree. It pulls the worktree with `--no-rebase`. It turns the mode on, writes `ci.json`, reads the signals and runs doctor. When an explainer page exists, it opens it at "Can you merge it?" before the first question, and says so. When the page is out of date, it builds it again first (`--no-rebuild` skips that) and says so in one line.

The first questions come in a fixed order. Each one is its own question:

1. **Bring the new PR commits into the review branch?** It shows when the PR head has commits that the review branch does not have. The options are these:
   - Merge, then re-check what they touch (`--merge`). It is a normal merge, never a rebase, a force-push or a push. A conflict undoes the merge and lists the files.
   - Show what the new commits change first (`--show-new`).
   - Skip, and re-check only the existing items (`--skip-merge`).
2. **Approve the CI profile?** Only the user approves it (`understando ci --approve`, or `--project <name>`).
3. **Link the new test to its claim?** One question for each test that the review branch added. A linked test becomes a check of its claim, with one planted bug: the code as it was before the fix (`restore-file`). The claim moves only after probe shows that the test goes red on that bug. An old test is never evidence for a new fix.
4. **Run the re-check?** It runs map, then probe on the changed code. When a model or a proof covers changed code, it runs the formal re-check too. That is the model check and its trace replay, with the approved formal commands.

## Run through

The recommended pick runs through: `understando review <pr> --go`. It stops only for the decisions of the user. These are the merge of new PR commits, the CI approval, invariants and claim wording, waivers, paid steps and publish. `--step` stops after each stage (map + probe, close, trim, ready + explain).

While a stop runs, it prints one plain line for each finished item, with ✓ or ✗. An example: "The idle stop: its new test caught the planted bug ✓". The full output of each verb goes to `$R/logs/review-<verb>.log`, and `--verbose` shows it. After the stop, it reports what was checked, what passed and what changed for the reviewer. Then it asks one question. `--json` gives the progress lines as NDJSON events with an `id`, then one JSON object.

A step that fails is recorded with its reason. The next `understando review <pr>` asks to retry it or to skip it (`--skip <step>`). It does not run the same step again without a pick. A manual `understando probe` of the same scope at the same tip counts as the probe step.

## The teach stop

After map, in `--step` mode, and at the end of a run through, review offers "Walk me through the change". `understando review <pr> --teach` gives one turn. It opens the next part of the explainer (the story, the loop, what changed, the weakest promise) and adds only what the page cannot. The rules are in [../references/adapted/teach.md](../references/adapted/teach.md): two to four ideas, the code by `understando snippet` refs, the claim and the check behind each guarantee, and one question. When no page exists, "Build the explainer first" is the recommended option.

## Close, trim, ready and explain

- **Close, one claim per question** ([close.md](close.md)). Put the pick in an answer file as `"close": {"answers": [...]}`, then run `understando review <pr> --go --answers <file>`.
- **Trim** ([trim.md](trim.md)). The user decides each "excess or untested" item.
- **Ready + explain.** It prints the four gates, builds the explainer and prints `pr-section.md`. Give the text to the user to paste. Do not edit the PR description.

## Before each hand edit on the ready branch

Before `formalize` or a hand edit changes a file, run `understando review <pr> --guard <path>[,<path>]`. It refuses a secret path, a protected path, unpulled commits on origin and a live lock of another writer.

## The answer file

`{"go": "step" | "run through", "merge": "yes" | "skip", "link": "yes" | "no", "ci": "approve", "ci_project"?: "<name>", "close": {"answers": [...]}, "paid": ["V36"]}`. Write `merge`, `ci` and `paid` only after the user picked that option in this conversation.

## State

`$R/review.json` holds the resolved context, the finished, failed and skipped steps, the merge and link decisions, the teach turn and the run time of each step. `--full` adds the full state, and `--verbose` adds the details (IDs, SHAs and paths).
