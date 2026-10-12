# Control catalogue

A control plants one defect that a verifier must see. Write at least one control for each verifier. Pick the **obvious** control: the defect that the verifier's name says it catches. A verifier that stays green on its obvious control gets the loud `cannot-fail` flag, and it does not count.

## Kinds

| Kind | What it plants | Who writes it |
|---|---|---|
| `planted` | One edit from the recipes below. | You, in a spec (`create`), with `build red --plant`, or a formal record |
| `stub` | The file as it was before the feature (`restore-file` at a commit). | `build red --stub PATH@REF` |
| `mutant` | Each mutant of a tool, on a function or on the riskiest changed lines. | `probe mutate` (mutmut, cosmic-ray) |
| `degraded` | A worse variant of an eval (a weaker prompt, a model, a corrupted label). It must score worse (`eval.score`, `eval.better`). | You |

[evidence-bars.md](evidence-bars.md) tells which control each surface needs.

## Recipes

| Recipe | Plant | Typical verifier |
|---|---|---|
| `remove-guard-line` | Remove the line that refuses, raises or returns early. | A test of a refusal |
| `invert-condition` | Turn `>` into `<=`, `if x` into `if not x`, or `-` into `+`. | A test of a branch or a value |
| `remove-type-pin` | Remove the `ignore` marker of a type pin, so the type error shows. Or widen the type that the pin guards. | A type-system pin |
| `drop-allowlist-row` | Remove one row of an allowlist that a real edge uses. | A static boundary check |
| `corrupt-golden-byte` | Flip one byte in a golden file. | A golden or parity test |
| `remove-covered-code` | Replace the body that a test claims to cover with a stub. | Any test |
| `plant-violation` | Add one line that breaks the rule, for example a forbidden import. Use it when no catalogue edit can reach the rule. | A boundary check, a contract format check |

## Edit operations

Each control holds a list of `edits`. `scripts/run_control.py` applies them in a fresh scratch worktree and refuses an edit that does not apply exactly.

Write an anchor op. It names its place with `path`, `symbol` (a dotted name at the head) and `match` (a text that occurs once in the symbol). A `match` of the form `/RE/` is a regex, and a regex group is the target. The probe resolves the anchor at the commit. An anchor that matches 0 places or more than 1 is an `ANCHOR ERROR`. Do not copy code into a `find` text.

| `op` | Fields | Effect |
|---|---|---|
| `delete-line` | `path`, `symbol`, `match` | Removes the target lines. In Python, removes the statement that starts on the target line, with its block. An empty block gets `pass`. |
| `invert-condition` | `path`, `symbol`, `match` | Python: negates the smallest condition, operand or comparison that holds the target. `a > b` becomes `a <= b`, `x` becomes `not x`. |
| `replace-with` | `path`, `symbol`, `match`, `with`, `span` (`match` or `statement`) | Replaces the target, or the whole Python statement on its line, with `with`: one line, 80 characters or fewer. |
| `drop-allowlist-row` | `path`, `symbol`, `match` | Python: removes the list, tuple, set or dict item that holds the target, with its comma. |
| `replace` | `path`, `find`, `replace`, `count` (default 1) | The old text form. The `find` text must occur exactly `count` times. |
| `append` | `path`, `text` | Adds `text` at the end of the file. |
| `corrupt-byte` | `path`, `offset` (default: the middle), or an anchor | XORs one byte with 0x01: the first byte of the target, or the byte at `offset`. |
| `delete-file` | `path` | Removes the file. |
| `restore-file` | `path`, `at` | Puts back the file as it was at the commit `at`: a stub. A new check must go red on the code before the feature. |

## Expected red

Each control sets `expect.status` to `red`. Set `expect.pattern` to a regex that the red output must hold, for example the test name or `file.py:36`. The pattern stops a red for the wrong reason from counting as a catch.

## Tier-1 proof standards

An e2e verifier proves a behaviour only when it drives the app as a user does. These rules come from the proof standards of create-verification-skill and maintain-verification-skill.

- **Drive the real user path.** Start the CLI or the service in its own process. Send the HTTP request, or drive the browser or the terminal. Do not call internal setters, test-only endpoints or the functions under the CLI.
- **Capture the action and the resulting state.** Record what the test did and the state after it. The last screen or the exit code alone is not enough.
- **Check the side effects.** Look at the files written, the rows inserted and the messages sent, together with what the user sees.
- **Mock only at a real boundary.** Use a fake only where a production boundary already isolates the external system.
- **Observe what a dry-run skips.** A dry-run or a test mode can still touch the network or a git ref. Observe the files, the network and the refs. Do not trust the name of the mode.
- **Cleanup keeps the evidence.** Remove the instances and the scratch state that the run made, never the proof. Check that the evidence is still at its named place after the cleanup.

## Mutants

A mutant is a control that a tool plants (`understando probe mutate`, [../commands/probe.md](../commands/probe.md)). A killed mutant made a test fail; a survivor is a change in the code that no test sees. The kill matrix records, for each mutant, which covering test killed it, each test run alone. Before a survivor counts, the equivalent-mutant filters run: the same bytecode as the original (trivial compiler equivalence, docstrings removed), the same syntax tree (a docstring or the layout), or a change only in the text of an error, log or print message. Each survivor needs a test that kills it, or a reason that the user accepts.

## Expensive evidence

Record evals and paid e2e runs as checks with `recorded` evidence and its provenance. Run them again only after a cost projection and a clear yes from the user.
