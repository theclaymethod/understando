# Understando eval scenarios

Working index from the developer interview. Each entry describes behavior to evaluate in Understando itself.

## Review work from a session

The deliverable is a list of checks that together express the intended behavior. Use the session to draft them and the interview to resolve choices that affect their expected outcomes. For each check, describe the situation and the observable result. Identify what existing verifications establish and where a new check is proposed.

| ID | Situation | Expected Understando behavior |
| --- | --- | --- |
| R1 | The request, later corrections, and examples together establish a rule. | Reconstruct the current rule from the session and identify its edge cases. An independent subagent may help read the session. |
| R2 | Two readings of the session imply different outcomes for the same case. | Put that case to the developer and ask which outcome they intend. |
| R3 | The owner forbids duplicate deliveries. A passing check counts queued requests. | Identify the verification needed at the delivery boundary, explain what the queue check actually covers, and surface the missing coverage. Distinguish an unverified delivery outcome from an observed duplicate. |
| R4 | Retry and ordinary delivery each have a passing test. The session forbids duplicate delivery. | Identify the missing combination: the first delivery succeeds, its acknowledgment is lost, and a retry follows. Propose checking that the recipient gets exactly one invitation. In a session review, this proposed check is a deliverable. An explicit request to verify the change also calls for creating and running it when supported. |
| R5 | Asked to decide an unresolved outcome, the developer says they are unsure. | Recommend an outcome and explain the reason. Walk through a concrete consequence of that choice and of a plausible alternative. Show how the choice changes a check. Keep the recommendation provisional until the developer decides. |

## Design verification from a spec

Given a proposed change, help the developer narrow the spec and codify it in checks they can use to judge the change.

| ID | Situation | Expected Understando behavior |
| --- | --- | --- |
| F1 | A proposed workflow has several independently observable promises. | Break it into those promises, identify the boundary cases, and propose verification types that can distinguish acceptable from unacceptable behavior. |
| F2 | Several proposed checks cover overlapping parts of the spec. | Help the developer narrow the set while retaining coverage for materially different outcomes. Show which promise each retained check would establish. |

The [session correction eval](evals/session-correction/README.md) exercises R1 and R2 by comparing the check list across a correction, including a boundary the developer leaves open or resolves. The [verifier-intent tickets](evals/verifier-intent/rubric.md) exercise evidence scope with paired confirmed and unconfirmed conditions.
