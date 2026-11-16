# Coverage of `new_task` in the model prompt

**Build 31: partial coverage.** Only the explicit `false` case has been verified at the boundary the developer specified: the final prompt sent to the model. The largest gap is unattended mode, where the model could still be offered `new_task` even though no preview dialog opened.

The [developer’s decisions](session.txt#L1) require `new_task` to be absent from the assembled prompt when `unattended` is `true` and offered in ordinary interactive mode. The [compatibility clarification](session.txt#L3) makes an omitted flag equivalent to `false`. Blocking a direct call outside the prompt remains undecided; registry membership is not an acceptance criterion.

Use one otherwise identical generic-model session per row. Capture the final outbound prompt after tool assembly and inspect its offered-tool names for the exact name `new_task`. For the legacy case, omit the setting from the input entirely so the check exercises the actual defaulting path.

| Input condition | Required observation in final prompt | Check and evidence |
| --- | --- | --- |
| Unattended, `true` | `new_task` absent; fail if offered, even if never called | **Proposed:** capture an unattended prompt. [Runner C, build 31](session.txt#L6) observed no preview during one task; it did not inspect the prompt. |
| Interactive, explicit `false` | `new_task` present; fail if removed globally | **Verified:** [Runner B, build 31](session.txt#L5) captured the final outbound generic-model prompt and found `new_task`. Retain this check. |
| Interactive, flag omitted | `new_task` present; fail if omission hides the tool | **Proposed:** repeat Runner B’s capture with a legacy input that has no flag. No final prompt was reported for this case. |

[Runner A, build 31](session.txt#L4) passed all three cases at the availability predicate. Keep that as supporting evidence: it verifies the predicate’s answers, but cannot detect prompt assembly ignoring them. The report does not establish readiness on this contract until both proposed prompt checks pass.
