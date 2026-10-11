# discover

Find the invariants of a PR, a code area or a claim **with the user**, before any verifier exists. Start it only on an explicit request from the user. The user's answers define each invariant. This verb stops for the user at each decision, also under full autonomy.

Each stop of this playbook ends with one question to the user. Ask it as [Asking the user](../references/working-rules.md#asking-the-user) tells you: the situation, a Next line, and numbered options.

For the question rounds, use the grilling skill when `understando routes` shows it installed, else [../references/adapted/grilling.md](../references/adapted/grilling.md).

## Steps

1. **Mine the candidates.** Run `understando discover [--paths <dir>/] [--claim C01]`. It reads the code at the head: guards, asserts, early returns, type narrowing and the result of a short function. It also reads the tests, the controls, git history (`git log -S`, fix commits), the PR text and the journal prompts. Each candidate is one plain line with its evidence (file:line, commit).
   - **Done when** `discover status` prints the candidate count.
2. **Ask the edge-case questions.** Run `understando discover questions`. Ask the user the one to three questions of each candidate, one candidate at a time, riskiest first. Each question names a boundary input, an odd event order or a failure part-way through. Give no answer in the question.
   - **Done when** the user answered or skipped each question of each candidate.
3. **Let the user write the statement.** Propose a wording when it helps. Write `"confirmed": true` only after the user says yes to the exact text. Put each concrete answer in `examples` (`expr` and `expect`, or `raises`), so the code at the head checks it.
   - **Done when** each candidate has a decision in the answer file: accept, reword (the user's text), reject (with the reason) or defer.
4. **Record.** Run `understando discover answer --answers <file>`. It writes one `invariant` row per decision to the journal. It copies each invariant to the trust map with its suggested tier (rule 5, process 4, wiring 3, input space 2, flow 1). It adds the frog EV score: the risk times the cost of an error, divided by the effort. It links the claims that the answer names. An example that the code does not give prints a finding in the find-bugs format ([../references/adapted/find-bugs.md](../references/adapted/find-bugs.md)). The heading is `P1 — [Small fix, 95% finding confidence, 90% fix confidence] <one line>`. Then come the trigger, expected and actual, and the evidence. Put the rating in the answer (`"rating": {"priority", "fix", "finding_confidence", "fix_confidence", "fix_direction"}`). A rating that nobody gave shows as "not rated". An answer that the user accepted is a verified bug. An answer that the user did not accept is a lead.
   - **Done when** `discover status` prints `DONE`. Report each possible bug and each `proposed` invariant to the user.

To take the proposed invariants of a formal sidecar, run `understando discover import --sidecar ~/.understando/runs/<repo>/<pr>/formal/verifiers.json`. Each invariant becomes a candidate with its questions, and the code's current behaviour is its evidence. Each question that the pilot marked unclear becomes a candidate of its own. A deferral can name an `owner` and a `flag`. Then run `understando formalize --sidecar` with the same file, so each record takes the user's decisions.

An invariant without `"confirmed": true` is `author: agent`, status `proposed`. No verifier may use it, except under full autonomy (`mode on --autonomy`), and then its claim stays at Backed or below.
