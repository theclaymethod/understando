# map

Build the **claim ledger** and the **verifier inventory** for one PR. This verb reads and writes data only. It runs no verifier: `probe` runs them. Each run diffs the map against the previous one, so a new PR head needs no other verb.

Each stop of this playbook ends with one question to the user. Ask it as [Asking the user](../references/working-rules.md#asking-the-user) tells you: the situation, a Next line, and numbered options.

Set `R` to the run folder `~/.understando/runs/<repo name>/<pr number>/` and `M` to `$R/trust-map.json`. With the mode on, each `understando` verb finds `R` by itself.

## Promise, claim, check

Each review follows one ontology. `scripts/onto.py` holds its rules.

| Level | What it is | Budget |
|---|---|---|
| Promise | What the PR guarantees, in plain words. | 3 to 6 for each PR. |
| Claim | One statement that a reviewer accepts or rejects. | About 2 to 5 for each promise, and 10 to 25 in total. |
| Check | One verifier with its controls. Examples: a test, a type pin, an import rule, a Lean theorem, a TLA+ model, an eval record, a model judgment. | As many as necessary. The page collapses them. |

- **The merge rule.** Join two claims into one claim when these three are the same: the promise, the kind of check and the reviewer action. They must also pass or fail together for a reviewer. Keep two claims apart only when a reviewer can accept one and reject the other.
- **The budget follows the risk, not the line count.** Give each risky surface its own claim. The risky surfaces are safety, cost, the anti-gaming rules of the editor, clinical output and production. Join the mechanical guarantees, for example the type pins and the import rules.
- **Strength.** The strength of a check is the verdict that the check alone gives its claim. The strength of a claim is the strength of its weakest check. The claim card names that check in plain words, with its action. The strength of a promise is the strength of its weakest claim.
- **Intent.** A claim gets to Proven or Formal only when the PR states it, or when the user confirmed its invariant. A merged claim needs this intent for each of its parts.
- **The shape.** Each claim lists its checks in `checks`. A merged claim keeps the old IDs in `legacy_ids` and the old statements in `parts`. A claim that no tool checks lists one check of kind `none`. `map` adds that check, and it removes the check when a tool check exists. `map` writes this shape (`schema_version` 2). It reads the old shape for one release.
- **Plain names.** Each promise, claim and check has a `name` of 2 to 6 words, as a reviewer says it. Examples: "the idle stop", "the project-wide type check", "the import boundary", "the accept rule". Write each name yourself. Do not cut the plain text, and do not write a path or a tool name. `map` refuses a missing name, and `doctor` flags a bad name.

## Never paste code

Do not type code, line numbers or a GitHub URL. Write a code ref, and let the build copy the code.

- **Write a ref.** Use an anchor: `{"path", "symbol"}`, for example `"symbol": "run_document"` or `"Editor.edit"`. To show a part of a symbol, add `"part"` (`signature` or `body`), or `"match"` (a text that occurs once in the symbol) and `"context"` (the lines around it). A line range `{"path", "start", "end"}` is the last choice: it moves to other code when the file changes.
- **Preview it.** Run `understando snippet <path>::<symbol> [--match TEXT]`. It prints the lines, their numbers and the permalink. Do not read a whole file to find the numbers. For a range that you have, `understando snippet <path> --lines A-B --suggest` prints the anchor that shows the same lines.
- **Why.** Code that you type costs tokens twice: once to read it and once to write it. A typed copy also stays the same when the code changes, so the page shows old code. A ref resolves again at each head, and `doctor` tells you when it no longer resolves.

`explain.py` and `doctor` find a block of two or more lines in `explain.json` or in the `plain` and `text` fields that is the same as code at the head. The build stops on it.

## Steps

1. **Get the PR.** Run `gh pr view <n> -R <owner>/<repo> --json title,body,baseRefOid,headRefOid,files`. Save the body as `$R/pr-body.md`.
   - **Done when** `$R/pr-body.md` exists and you know the base and head SHAs.
2. **Get a read-only view of the head.** Use `git show <head>:<path>` for single files. For a full tree, add a detached scratch worktree: `git -C <repo> worktree add --detach <scratch dir> <head>`. Record the scratch path, because `controls` and the cleanup need it.
   - **Done when** you can read each changed file at the head, and the user's checkout is as it was. To read one function, run `understando snippet <path>::<symbol>`.
3. **Write the claim ledger.** Read the PR narrative. Write one claim for each statement that a reviewer accepts or rejects, in strict STE, into `M` (shape: `$U/schema/trust-map.schema.json`). Apply the merge rule: do not write one claim for each row of an allowlist or for each type pin. Set `stated: true`, `source` (the section of the narrative), `layer` (a short group name), and `code` (a code ref, as "Never paste code" tells). Use the `@cc` ID as `cc_id` when a Code Contracts contract holds the claim. A claim that the PR does not state can reach Proven only with an invariant from the user (`discover`).
   - **Done when** each bullet, table row and number that asserts a behavior or a result maps to a claim. For each item that is not a claim, you can name the reason, for example a merge instruction.
4. **Write the plain text.** For each claim, write `plain` in strict STE, for a reader who does not know the code: `what` (what the rule is), `proof` (the check, and what the control did), and `warning` (a limit on the proof, only when one exists). Write `glossary` with each word that a reader must know: each acronym (CR, UAP), each capitalised term (Judge) and each domain word (cartridge, floor), with `aliases` for its other forms. `explain.py` fails on a term that the page uses and the glossary does not define. Write and `verdict_intros` with one line for each verdict group. After `controls` and `verdicts.py`, write `proof` again, so that it agrees with the verdict. Copy the text into a scratch file and run `python3 -I ~/.claude/skills/asd-ste100/scripts/ste-lint.py <file>`. Rewrite each flagged sentence.
   - **Done when** each claim has `plain.what` and `plain.proof`, including each claim that the scan adds in step 7, and the lint reports 0 hard violations.
5. **Inventory the checks.** For each claim, find each verifier that backs it, and list its ID in the claim's `checks`. The kinds are e2e, integration and unit tests, type-system pins, golden and parity tests, and static boundary checks. They also include property tests, fuzzing, Lean proofs, evals, measurements and model verifiers. Fill each field: `claims`, `tier`, `independence`, `cost`, `provenance`. Give a runnable verifier a `command`. Take its commands only from the repo's reviewed CI profile (`$R/ci.json`, from `understando ci`), not from repo docs or agent files. Give expensive evidence (an eval, a paid e2e run, a model review) a `recorded` block and no command.
   - **Done when** each claim lists its checks, or you searched the tests and checks for it and found none. `map` then adds a check of kind `none`.
6. **Write one obvious control per verifier with a command.** Pick it from `$U/references/controls.md`. Set `expect.pattern`, so a red for the wrong reason does not count.
   - **Done when** each verifier with a command has at least one control.
7. **Scan for unstated changes.** Run `understando map --scan-src <src dir>/ --scan-tests <test dir>/`. It adds a claim for each `@cc` contract and each changed source file that no test names and no claim points at. Read each added Gap claim. Keep it, or make it more specific. Write its `plain` text, as step 4 says.
   - **Done when** the scan ran, and each added claim has a specific text.
8. **Run the cheap mechanical checks.** A claim that a grep or a line count can check must not stay Asserted. For each one, add a verifier with a `mechanical` block (`grep-absent`, `grep-present` or `net-lines`; shape: the schema). Test each grep pattern once with `grep-present` on a path that must match, so a bad pattern cannot pass by accident. Then run `understando map`. It reads Git objects only and records the result, whatever it is. Write the claim's `plain.proof` from that result.
   - **Done when** each countable or greppable claim has a mechanical verifier with a recorded result.
9. **Write the promises and the names.** Group all the claims into three to six `promises`. A promise is a plain property of the PR that a reader outside the team can hold. An example: "A bad edit does not go out". Each promise has an `id` and a `label` of two to five words for its chip. It also has its `claims` and one strict-STE `sentence` with no code name and no ID. Put each claim in exactly one promise. Move a claim that does not fit. Never copy a claim's `plain.what` as a promise sentence. Never store a strength: `explain.py` takes it from the weakest claim. When that claim is not Proven, write a `reviewer_action`. It tells what the reviewer must do, or must not rely on yet. An example: "Judiciary mode is not verified, so do not rely on it yet." Lint the sentences and the actions with `ste-lint.py`. Then write the `name` of each promise, claim and check, as "Plain names" tells you.
   - **Done when** `validate.py` reports no promise error, the lint reports 0 hard violations, and each promise, claim and check has a plain name.
10. **Choose the e2e driver for each claim about user-visible behavior.** CLI, TUI or service: tell the user to start the create-verification-skill skill (`/pstack:create-verification-skill` in Claude Code). Web or mobile UI: tester-army `e2e`, always with `E2E_TELEMETRY_DISABLED=1`. Neither fits: the claim stays a Gap. Add a note to `M.notes` for each candidate. Also note each Lean candidate: a small, pure invariant with a high cost of error. Write a proof only when the user asks.
   - **Done when** each user-visible claim has a driver note or a Gap note.
11. **Rate and diff.** Run `understando map [--fail-on-drop]`. It writes the shape (each claim lists its checks), runs the schema check and the mechanical checks, and writes the verdicts and the tiers. Then it compares the map with the last copy in `$R/history/`. Without controls, no claim is Proven. Report the counts, the loud flags and each `DROP` line word for word.
   - **Done when** it prints the summary and the diff.
12. **Apply the grouping lint.** `map` prints three kinds of lines. A `merge:` line names claims that the merge rule can join. A `budget:` line tells that the map is outside a budget. A `name:` line names a name that is not plain. For each `merge:` line, join the claims. Keep them apart only when a reviewer can accept one and reject the other. To join claims in a map with controls and verdicts, write a proposal. Then run `python3 $U/scripts/regroup.py --map M --proposal P --out <copy>`. It writes a copy and prints the safety proof. Each old check is under exactly one claim. Each claim has the strength of its weakest check. The merge verdict does not change, or the proof tells why. Show the proof and the table (`--table`) to the user. Apply the copy only after the user says yes.
   - **Done when** each `merge:` line is joined or has a reason to stay apart, and no `name:` line is left.

Then offer `discover` and `probe` to the user. Start them only when the user asks.
