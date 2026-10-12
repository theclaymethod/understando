# Verifiers: what counts, by surface

A verifier counts when its control makes it fail. For each behavior, pick the strongest practical verifier for its surface. Each section has the same four parts: what counts, the tool, the control and the evidence.

## Backend

- **What counts.**
  - A risky invariant (money, safety, data loss, production): a proof. Use Lean for a pure rule. Use TLA+ for a loop, a retry, a state machine or concurrency. Each proof needs conformance against the real code ([formal.md](formal.md)).
  - A rule with a contract: a Code Contract (a `@cc` contract states the invariant, and a check with a control proves it; [formal.md](formal.md#code-contracts)).
  - Wiring: a type pin (pyright or basedpyright), an import rule, or a property test (Hypothesis). Put the weight of a generator on the boundaries: each guard's threshold ±1, empty, one item, duplicates, ties.
  - A plain example test alone is below the bar for a risky invariant.
- **Tool.** `scripts/lean-check.sh`, `scripts/tlc.sh`, `cc-check`, `basedpyright`, Hypothesis under the project's own test command, and `scripts/mutate.sh` (mutmut).
- **Control.** A planted bug in the real function (delete the guard, invert a condition) with `scripts/control.sh`, or mutation testing with `scripts/mutate.sh` on the changed functions. Review each survivor. A survivor is harmless (the same behavior: an equivalent mutant, or a change only in the text of a message) or a real gap (write a test that kills it). For a proof, a planted wrong model must break the proof, and a planted wrong function must break conformance.
- **Evidence.** The command, its exit code and its output. For a proof, the receipt in formal.md. For mutmut, the counts of killed and survived mutants, and the reason for each harmless survivor.

## Frontend

- **What counts.** A real-browser e2e that drives the user path: tester-army `e2e`, `expect`, or Playwright. A component test is below the bar.
- **Tool.** The browser harness that the repo has. Else `expect`, then Playwright.
- **Control.** Break the UI behavior (remove the handler, hide the control, change the route). The run must fail.
- **Evidence.** A recorded video and screenshots of the action and of the resulting state.

## LLM

- **What counts.** A recorded eval with a frozen judge or frozen labels. Make it blind where possible: the judge does not see which variant made the output. Run k of 3 or more for each item. Record the provenance: the model IDs, the prompt hash, the dataset version and the commit.
- **Tool.** The eval harness of the repo.
- **Control.** A degraded variant (an ablated prompt, a weaker model, shuffled input) must score measurably worse: outside the spread of the k runs. An eval that never had a degraded variant cannot show that it can fail.
- **Evidence.** The score of each variant and each run, the judge version and the provenance. Before a paid run, show the cost estimate and wait for the user's yes.

## General rules

- Take the evidence from the real user path: run the CLI in its own process, send the HTTP request, drive the browser. Do not use internal setters or test-only endpoints. Capture the action, the resulting state and the side effects (files written, rows inserted, messages sent).
- Use a mock only where a production boundary already isolates the external system.
- A red counts only for the right reason: the failure names the test, the line or the behavior.
- Cleanup removes the instances and the scratch state. It keeps the evidence.
- Say how strong a claim is. A part is as strong as its strongest verifier that caught its planted bug: Formal (a proof with conformance), Proven (a lower verifier), Backed (verifiers exist, none proven to fail), Gap (no verifier). A claim is as strong as its weakest part. A part on an agent-picked invariant stays at Backed.
