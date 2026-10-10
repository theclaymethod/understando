# Control catalogue

A control plants one defect that a verifier must see. Write at least one control per verifier that has a command. Pick the **obvious** control: the defect that the verifier's name says it catches. A verifier that stays green on its obvious control gets the loud `cannot-fail` flag.

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

| `op` | Fields | Effect |
|---|---|---|
| `replace` | `path`, `find`, `replace`, `count` (default 1) | The `find` text must occur exactly `count` times. |
| `append` | `path`, `text` | Adds `text` at the end of the file. |
| `corrupt-byte` | `path`, `offset` (default: the middle) | XORs one byte with 0x01. |
| `delete-file` | `path` | Removes the file. |

## Expected red

Each control sets `expect.status` to `red`. Set `expect.pattern` to a regex that the red output must hold, for example the test name or `file.py:36`. The pattern stops a red for the wrong reason from counting as a catch.

## Expensive evidence

Record evals, paid e2e runs and model reviews as `recorded` verifiers with their provenance. Run them again only after a cost projection and a clear yes from the user.
