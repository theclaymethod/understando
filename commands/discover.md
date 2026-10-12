# discover

The user states the invariants of a feature, through edge-case questions, before any verifier exists. Start it only on an explicit request from the user. This verb stops for the user at each decision.

For the question rounds, use the grilling skill when it is installed, else [../references/adapted/grilling.md](../references/adapted/grilling.md).

## Steps

1. **Mine the candidates.** Run `understando discover --feature F` (or `--paths P`). It reads the code at the head: guards, asserts, early returns, type narrowing and the result of a short function. Each candidate is one plain line with its evidence: the line, the tests that name the function, and the commits and fix commits that touched it.
   - **Done when** `discover status` prints the candidate count.
2. **Ask the edge-case questions.** Run `understando discover questions`. Ask the user the one to three questions of each candidate, one candidate at a time, riskiest first. Each question names a boundary input, an odd event order or a failure part-way through. Give no answer in the question.
   - **Done when** the user answered or skipped each question.
3. **Let the user write the statement.** Propose a wording when it helps. Write `"confirmed": true` only after the user says yes to the exact text. Put each concrete answer in `examples` (`expr` and `expect`, or `raises`), so the code at the head checks it. Mark a risky invariant `"risky": true`: its backend bar is a proof.
   - **Done when** each candidate has a decision in the answer file: accept, reword (the user's text), reject (with the reason) or defer.
4. **Record.** Run `understando discover answer --answers FILE`. Each decision becomes an invariant in the store, with its shape (rule, process, wiring, input space, flow) and the ladder rung that suits it. An example that the code does not give prints a finding in the format of [../references/adapted/find-bugs.md](../references/adapted/find-bugs.md); put the rating in the answer (`"rating"`). An answer that the user confirmed is a bug; else it is a lead.
   - **Done when** `discover status` prints `DONE`. Report each possible bug and each agent-picked invariant.

An invariant without `"confirmed": true` is `author: agent`, status `proposed`. A claim on it stays Backed, and the Verifier section marks it agent-picked.

`understando discover import --sidecar $R/formal/verifiers.json` takes the proposed invariants of a formal sidecar as candidates.
