# close

Close each Asserted or Gap claim with the user, riskiest first. Start it only on an explicit request from the user. The reword and waive options stop for the user, also under full autonomy.

## Steps

1. **Read the queue.** Run `understando close --list`. Gap claims come first, then claims with a loud flag.
   - **Done when** you have the queue and the seven options.
2. **Ask the user, one claim at a time.** Offer the seven options. Options 1 to 4 are a mechanical check, formalize (tier 4 or 5), a property test or a contract, and an e2e test. Then 5 recorded evidence, 6 reword or drop the claim, and 7 waive with a reason.
   - **Done when** the user chose an option for each claim, or chose to skip it.
3. **Draft.** For options 3 and 4, draft the test and one control (the planted bug that it must catch). Use the sequence-verifiable-units principle: one claim, one check, one control. A claim that the PR does not state needs an invariant from the user (`discover`), so name it in `invariant`.
   - **Done when** the answer file holds each choice. Its shape is in `understando close --help`.
4. **Apply.** Run `understando close --answers <file>`. A drafted test goes to a scratch clone. Probe runs it. When it is green, then red on its control, the commit goes to `understando/<pr>-ready`. A waiver shows in the ready checklist and in the PR section.
   - **Done when** it prints `DONE`, or each open claim has the reason why it stays open.
