# Evidence bars: which check to write

This file is guidance on which verifier to write for a feature. `scripts/strength.py` (`meets_bar`) and the Verifier section of each feature file (`scripts/create.py`, `BAR_TEXT`) implement it.

Each feature has a surface, and the surface sets the bar. Pick the strongest practical check on the ladder that meets the bar ([verdicts.md](verdicts.md)). Every verifier has a control that must make it fail ([controls.md](controls.md)); a verifier that cannot fail does not count.

| Surface | The feature | The bar | Its control |
|---|---|---|---|
| frontend | A user-visible UI behaviour. | A real-browser e2e that drives the user path, with a recorded video and screenshots as evidence (`evidence.require`, for example `*.webm` and `*.png`). A unit or component test is below the bar. | A planted bug in the UI code: the e2e must fail. |
| backend | Deterministic code, also code that handles model output (a gate, a refusal, a wiring path). | **Formal:** Lean or TLA+ with conformance against the real code, for a risky invariant. **Code Contracts:** a `@cc` contract states the invariant, and a check with a control proves it. **Types, import rules and property tests,** for wiring. An example test alone is below the bar. | A planted bug, a stub, or a mutant (`probe mutate`). For a proof: a wrong model, and for Lean a wrong function. |
| llm | The quality or the behaviour of model output. | A recorded eval with a frozen judge or labels (`eval.frozen`), with its score in the output (`eval.score`). | A degraded variant (a worse prompt, a weaker model, a corrupted label) must score worse. An eval with no degraded variant cannot show that it can fail. |
| other | No code and no model output. | A check that a control can make fail. | As above. |

## Choosing within the backend bar

- **A risky invariant** (money, safety, data loss, production; or `"risky": true` from discover): a proof. A pure rule goes to Lean (rung 5); a loop, a retry, a state machine or concurrency goes to TLA+ (rung 4). Use `understando formalize`, and the lean-formal-feedback-loop skill when it is installed.
- **A rule with a contract:** write the `@cc` contract with the code-contracts skill (when it is installed, else by hand), check its format with `cc-check format`, and back it with a check that runs the rule (`build check --kind contract --cc-id ID`). The contract states the invariant; the check with its control proves it.
- **Wiring:** a type pin, an import rule or a property test. A property test (rung 2) is the default for a rule with a large input space and no cheap model ([property.md](property.md)).

## Choosing the shape from discover

discover gives each invariant a shape. The shape suggests the rung: a rule 5, a process 4, wiring 3, an input space 2, a flow 1. The bar of the surface wins when the two differ: a flow on a frontend feature is a browser e2e; a rule on a backend feature that is not risky is a contract or a property test.
