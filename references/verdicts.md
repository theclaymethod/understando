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
| `absent` | A check of kind `none`: no tool checks the claim. | No |

A red result counts as caught only when the exit code is in `red_exits` (default `[1]`) and the output holds `expect.pattern`. A red for a different reason (an import error, a syntax error) is an error, not a catch.

## Check strength

A claim has parts: one part for each statement, each with its own checks (`claims[].parts[].checks`). A claim with no `parts` is one part with all its checks. The strength of a check is the verdict that the check alone gives its part:

| Strength | Rule |
|---|---|
| **Formal** | The check is on ladder rung 4 or 5, and it is `proven`: a control broke the proof or the model. Its `formal.conformance` link passes. |
| **Proven** | The check is `proven`, and it is fact tier. A model check also qualifies when its family is not the author's family, its context is fresh, and it went red on a control. |
| **Backed** | The check is `proven`, `untested`, `recorded` or `checked`. A same-family model check stays here, also after a control. A rung 4 or 5 check without a passing conformance link or a Formal record stays here. |
| **Asserted** | The check is `cannot-fail`, `failing`, `broken` or `stale`, or it is of kind `none`, and the PR narrative states the part. |
| **Gap** | The same, but the PR does not state the part. The reviewer decides. |

Intent gate: a Formal or Proven check gives only Backed when the part has no intent. A part has intent when the PR states it, or when the user accepted its invariant.

## Part and claim verdicts

- **A part** is as strong as its strongest check. Extra checks never lower a part. Thus, a backup test next to a proof keeps the part Formal.
- **A claim** is as strong as its weakest part. Thus, a merged claim cannot hide a part that no check proves.
- **A weak check is a flag, not a score.** A check can miss its planted bug, fail to fail, or fail at the head. Then the card shows a warning with an action, for example "1 of 5 checks missed its bug. Fix it or drop it." The check lowers its part only when it is the only evidence of that part.
- **One check for each formal property.** Each TLA+ invariant or property, and each Lean theorem group, is its own check with its own controls. It is under the part that it proves.
- **A possible bug** makes its part Gap: the code does not obey an invariant of the part that the user accepted.

The `tier` of a claim is the highest rung of a check that went red on a control and can prove the claim. The promise shows it as "Strongest check". The strength of a promise is the verdict of its weakest claim. `scripts/derive.py` derives each value, and the PR body, the review CLI and the page show the same value.

## Evidence bars

Each claim also has an evidence bar for its surface (frontend, backend, llm or other). [evidence-bars.md](evidence-bars.md) is the only source of the surfaces, the bars, their controls and how they change the merge verdict.

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
