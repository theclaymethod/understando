# Verdicts, verifier states and flags

`scripts/verdicts.py` is the only implementation of these rules. This file says what the rules mean. When the two disagree, the script is the fact and this file has a bug.

## Tiers

- **Fact tier:** a tool observed it. Examples: a test run, type-checker output, a golden test, a boundary check, a fuzz result and a recorded eval. An e2e transcript or a replay against the real app also counts, and so does `cc-check format`.
- **Guess tier:** a model judged it, or only text says it. Examples: model judgements, PR narrative, repros and `$code-contracts verify`.

## The verification ladder

Each claim gets `tier`: the highest rung of a check that went red on a control and can prove the claim. The rung comes from the verifier's `ladder`, else from its kind.

| Rung | Checks |
|---|---|
| 1 | e2e and integration tests (unit, golden, parity, eval and measurement also sit here) |
| 2 | property tests and fuzzing |
| 3 | type pins, `@cc` contracts, contract-format checks and static boundary rules |
| 4 | model checking (TLA+). It needs a passing conformance link. |
| 5 | a Lean proof. It needs a passing conformance link. |

A rung 4 or 5 verifier without a passing conformance link cannot prove its claim, so the claim stays Backed. A recorded proof control (`result.recorded: true`) counts as a control that went red.

## Verifier states

The script sets `state` on each verifier from its baseline and its control results.

| State | Rule | Can back a claim |
|---|---|---|
| `proven` | Green at the head, and at least one control went red with its expected pattern. | Yes |
| `cannot-fail` | Green at the head, no control went red, and at least one control stayed green. | No |
| `untested` | No control ran, or each control gave an error. | Yes |
| `recorded` | No command. The evidence is recorded with its provenance and is not run again. | Yes |
| `checked` | A mechanical check (a grep or a line count, `scripts/mechanical.py`) passed at the head. No control ran. | Yes |
| `failing` | Red at the head with no control, or a mechanical check that failed. | No |
| `broken` | The baseline did not complete. | No |
| `stale` | Imported evidence (`understando import`) failed its format check, or the file changed after the import. | No |

A red result counts as caught only when the exit code is in `red_exits` (default `[1]`) and the output holds `expect.pattern`. A red for a different reason (an import error, a syntax error) is an error, not a catch.

## Check strength

A claim lists its checks (`claims[].checks`). The strength of a check is the verdict that the check alone gives its claim:

| Strength | Rule |
|---|---|
| **Formal** | The check is on ladder rung 4 or 5, and it is `proven`: a control broke the proof or the model. Its `formal.conformance` link passes. |
| **Proven** | The check is `proven`, and it is fact tier. A model check also qualifies when its family is not the author's family, its context is fresh, and it went red on a control. |
| **Backed** | The check is `proven`, `untested`, `recorded` or `checked`. A same-family model check stays here, also after a control. A rung 4 or 5 check without a passing conformance link stays here. |
| **Asserted** | The check is `cannot-fail`, `failing`, `broken` or `stale`, or it is of kind `none`, and the PR narrative states the claim. |
| **Gap** | The same, but the PR does not state the claim. The reviewer decides. |

Intent gate: a Formal or Proven check gives only Backed when the claim has no intent. A claim has intent when the PR states it, or when each of its invariants has `author: user` and `status: accepted`. A merged claim needs this intent for each of its `parts`.

## Claim verdicts

The verdict of a claim is the strength of its weakest check. Two checks can have the same strength. Then the weakest is the check that is weak by itself, not only by the intent gate. After that, it is the check with the worst result. The results, worst first, are none, broken, cannot fail, missed, no planted bug, mechanical, recorded and caught. The claim card names this check, in plain words, with its action. Thus, a weak check cannot hide behind a strong check of the same claim.

A user-confirmed invariant of the claim that the code does not obey (a possible bug) makes the claim Gap.

The `tier` of a claim is the highest rung of a check that went red on a control and can prove the claim. It is the strongest check, and the verdict is the weakest check. The promise shows the tier as "Strongest check".

The strength of a promise is the verdict of its weakest claim. `scripts/derive.py` derives it, and the PR body, the review CLI and the page show the same value.

## Flags

| Flag | Loud | Meaning |
|---|---|---|
| `cannot-fail` | Yes | The obvious control stayed green. The verifier checks nothing that the control broke. |
| `fails-at-head` | Yes | The verifier is red at the PR head. |
| `baseline-error` | Yes | The verifier did not complete at the PR head. |
| `control-missed` | No | A `proven` verifier stayed green on one more control. It does not see that defect. |
| `control-error` | No | A control did not apply, or it gave an exit outside green and red. |
| `baseline-not-run` | No | The verifier has a command, but it did not run at the head. |
| `same-family` | No | A model verifier uses the author's model family: one opinion counted twice. |
| `shared-context` | No | A model verifier saw the PR narrative. |

Put each loud flag in the PR-body section and at the top of the explainer.
