# Strengths, check states and flags

`scripts/strength.py` is the only implementation of these rules: the other scripts read its report, and `scripts/derive.py` only words it for the explainer. This file says what they mean. When the two disagree, the script is the fact and this file has a bug.

## The verification ladder

| Rung | Checks |
|---|---|
| 1 | e2e and integration tests, recorded evals |
| 2 | property tests and fuzzing |
| 3 | types, `@cc` contracts (Code Contracts) and static rules, for example import rules |
| 4 | a TLA+ model check, with a passing conformance link to the real code |
| 5 | a Lean proof, with a passing conformance link to the real code |

A rung counts only after a control shows that its check can fail. A rung 4 or 5 check also needs a formal record that rates Formal ([../commands/formalize.md](../commands/formalize.md)).

## Check states

| State | Rule | Counts |
|---|---|---|
| `proven` | Green at the head, and a control made it fail (red with its expected pattern; for a degraded variant, a worse score). A recorded proof counts when its recorded control went red. | Yes |
| `untested` | Green, but no control ran. | No |
| `recorded` | No command, and no recorded control that went red. | No |
| `cannot-fail` | It stayed green on each of its controls. | No: report it first |
| `failing` | Red at the head with no control. | No |
| `broken` | It did not complete at the head. | No |

## Parts and claims

- A claim holds one part for each statement, and each part lists its checks. A claim with no parts is one part.
- **A part is as strong as its strongest check that caught its bug.** Formal: a proven rung 4 or 5 check. Proven: a proven check at a lower rung. Backed: checks exist, and none is proven. Gap: no check.
- **A claim is as strong as its weakest part.**
- **Intent.** Proven and Formal need each invariant of the part to be the user's (`author: user`, `status: accepted`, from discover). A part on an agent-picked invariant stays Backed, and the reason names the invariant.
- **The bar.** A claim meets its bar when each part has a proven check that meets the bar of the feature's surface ([evidence-bars.md](evidence-bars.md)). The bar does not change the strength: the two show side by side.

## Flags

| Flag | Loud | Meaning |
|---|---|---|
| `cannot-fail` | yes | The check stayed green on each control. It checks nothing that the control broke. |
| `fails-at-head`, `error-at-head` | yes | The check is red, or does not finish, without a control. |
| `control-missed` | no | A proven check stayed green on one of its controls: it does not see that bug. |
| `control-error` | no | A control gave no clean red or green (an anchor error, a wrong pattern). |
| `no-control`, `not-run` | no | Nothing shows yet that the check can fail. |

maintain adds `stale` (a check that was proven, and whose control no longer makes it fail), `stale-anchor` and `proof-drift` ([../commands/maintain.md](../commands/maintain.md)).
