# Understando eval scenarios

Working index from the developer interview. Each entry describes behavior to evaluate in Understando itself.

## Review work from a session

Start the review with a correctable account of the end-user experience. Use the developer’s response to revise the checks and reassess their evidence.

| ID | Situation | Expected Understando behavior |
| --- | --- | --- |
| R1 | The request, later corrections, and examples together establish a rule. | Reconstruct the current rule from the session and identify its edge cases. An independent subagent may help read the session. |
| R2 | Two readings of the session imply different outcomes for the same case. | Put that case to the developer and ask which outcome they intend. |
| R3 | The owner forbids duplicate deliveries. A passing check counts queued requests. | Identify the verification needed at the delivery boundary, explain what the queue check actually covers, and surface the missing coverage. Distinguish an unverified delivery outcome from an observed duplicate. |
| R4 | Retry and ordinary delivery each have a passing test. The session forbids duplicate delivery. | Identify the missing combination: the first delivery succeeds, its acknowledgment is lost, and a retry follows. Propose checking that the recipient gets exactly one invitation. In a session review, this proposed check is a deliverable. An explicit request to verify the change also calls for creating and running it when supported. |
| R5 | Asked to decide an unresolved outcome, the developer says they are unsure. | Recommend an outcome and explain the reason. Walk through a concrete consequence of that choice and of a plausible alternative. Show how the choice changes a check. Keep the recommendation provisional until the developer decides. |
| R6 | A UI-facing feature has passing backend/unit tests and a green typecheck, but no live browser run or visual evidence. | Credit the backend/unit coverage within its scope, explicitly withhold closure on the user-facing promise, and require an end-to-end live UI run against the real stack with screenshots and/or video recordings before marking the user-facing work done. |

## Design verification from a spec

Given a proposed change, help the developer narrow the spec and codify it in checks they can use to judge the change.

| ID | Situation | Expected Understando behavior |
| --- | --- | --- |
| F1 | A proposed workflow has several independently observable promises. | Break it into those promises, identify the boundary cases, and propose verification types that can distinguish acceptable from unacceptable behavior. |
| F2 | Several proposed checks cover overlapping parts of the spec. | Help the developer narrow the set while retaining coverage for materially different outcomes. Show which promise each retained check would establish. |
| F3 | A backend spec defines concurrent state transitions, retries, or cursor/ordering invariants. | Route verification to formal methods (model checking / statecharts such as TLA+, using PStack’s `create-formal-verification-skill`, `/statechart`, and `find-state-machines` when available), state bounds and assumptions, and require code-level mapping and replay rather than relying on unit tests alone. |
| F4 | A feature combines an LLM-driven judgment step, a stateful backend write path, and a user-facing UI view. | Split verification by modality and scope: contrasting-example eval (CStack `create-eval`/`run-eval` when available) for the LLM judgment, formal model plus code-level replay/integration check for backend state/concurrency, and live end-to-end browser run with screenshots/video for the UI journey. |

The [session correction eval](evals/session-correction/README.md) exercises R1 and R2 by comparing the check list across a correction, including a boundary the developer leaves open or resolves. The [verifier-intent tickets](evals/verifier-intent/rubric.md) exercise evidence scope with paired confirmed and unconfirmed conditions.

## Efficient discovery

| ID | Situation | Expected Understando behavior |
| --- | --- | --- |
| D1 | Two rules fit the same green run. Different owners give opposite decisions about a single changed condition. | Ask one question that separates the rules. The resulting proposed checks should predict opposite observable outcomes under the two answers. Keep the ordinary observation, allowed alternatives and deferred case intact. |
| D2 | The session already records the deciding condition, the owner’s rule and a direct observation. | Credit that observation, respect its scope and finish without asking the owner to settle the rule again. |
| D3 | A grader misses a confirmed failure while another boundary is still undecided. | Use the available CStack primitives to probe the check. Separate the observed grader defect from the unresolved product choice and return a distinguishing question. |
| D4 | A reviewer proposes arithmetic testing above the supported checkout limit. Execution shows checkout rejects the transaction before computing the total. | Check the guard on the relevant path. Spend zero owner questions and add zero product eval rows for the prevented failure. |
| D5 | The same checkout limit applies, but an allowed multi-item purchase produces a wrong total and all existing evals use quantity one. | Preserve the guard finding. Identify the reachable quantity-related failure as distinct and derive the expected result from the existing arithmetic promise. |

The [shared discovery replay](https://github.com/theclaymethod/cstack/tree/main/evals/spec-discovery) runs D1 and D2 with either skill. The [composition exercise](evals/spec-discovery/README.md) evaluates D3 using a runnable grader and installed skill files.

The [two-pass replay](evals/two-pass/README.md) exercises a review corrected mid-interview and a fresh spec that calls for different kinds of evidence.
