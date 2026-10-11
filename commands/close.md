# close

Close each Asserted or Gap claim with the user, riskiest first. Start it only on an explicit request from the user. The reword and waive options stop for the user, also under full autonomy.

Each stop of this playbook ends with one question to the user. Ask it as [Asking the user](../references/working-rules.md#asking-the-user) tells you: the situation, a Next line, and numbered options.

## Steps

1. **Read the queue.** Run `understando close --list`. Gap claims come first, then claims with a loud flag.
   - **Done when** you have the queue and the seven options.
2. **Ask the user, one claim at a time.** Run `understando close --next --json`, and relay its `prompt`. It holds one claim in one plain sentence, and why the claim is weak. Then it holds three options: the recommended one first, then the rest cheapest first. "Something else" holds the other options. They are a mechanical check, formalize (tier 4 or 5), a property test or a contract, and an e2e test. They are also recorded evidence, reword or drop, and waive with a reason. Never ask about all the claims in one question.
   - **Done when** the user chose an option for this claim, or chose to skip it. Then ask about the next claim.
3. **Draft.** For options 3 and 4, draft the test and one control (the planted bug that it must catch). Use the sequence-verifiable-units principle: one claim, one check, one control. A claim that the PR does not state needs an invariant from the user (`discover`), so name it in `invariant`.
   - **Done when** the answer file holds each choice. Its shape is in `understando close --help`.
4. **Apply.** Run `understando close --answers <file>`. A drafted test goes to a scratch clone. Probe runs it. When it is green, then red on its control, the commit goes to `understando/<pr>-ready`. A waiver shows in the ready checklist and in the PR section.
   - **Done when** it prints `DONE`, or each open claim has the reason why it stays open.
