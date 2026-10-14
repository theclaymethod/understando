# build: verifier-first work on a behavior

Write the verifier before the code, and prove that it can fail. What counts for each surface is in [../references/verifiers.md](../references/verifiers.md). Proofs are in [../references/formal.md](../references/formal.md). When the tdd skill is installed, use it for the red-green rhythm; the steps here set the bar.

## The order

The order is the rule: invariant, verifier, red, code, green. Do not edit a source file before step 4 is done. Tests, specs, `formal/`, `*.lean`, `*.tla` and verify skills are the files you may edit first. If you find that you edited source early, stop, revert that edit, and go back to step 3. The user can say to skip verifier-first; then say so in the report.

## Steps

1. **Ask the user for the invariant.** Ask edge-case questions, one behavior at a time: a boundary input, an odd order of events, a failure part-way through ("what should happen if the amount equals the balance?"). Give no suggested answer.
   - **Done when** the user's answers state the invariant and you wrote them down in the user's words. An invariant that you pick is marked agent-picked, and its claim stays at Backed or lower until the user accepts it.
2. **Choose the verifier.** Take the strongest practical verifier for the surface. A risky backend invariant gets a proof (Lean, TLA+) or a Code Contract with a check.
   - **Done when** you can name the verifier, its tool, its command and its control.
3. **Write the verifier.** Write the e2e or integration test, the property test, the contract or the model, in the working tree, next to the code that it tests.
   - **Done when** one command runs it.
4. **Prove that it fails.** Show the command, then run it after the user says yes. For new behavior, run the verifier on the code that you have. For a behavior that exists already, plant a bug in a throwaway copy (the arguments are those of `control.sh`):

   ```bash
   "$U/scripts/control.sh" --replace PATH 'GUARD TEXT' 'BROKEN TEXT' -- <the verifier command>
   "$U/scripts/control.sh" --patch stub.diff -- <the verifier command>      # a stub, or a deleted guard
   ```

   - **Done when** you have shown the user the failure output, and it names the behavior, not a typo or a missing import. A verifier that passes before the code exists tests nothing new: make it test the behavior that the code must add.
5. **Write the code.** For a proof, run `"$U/scripts/lean-check.sh" --dir formal/lean --import MODULE THEOREM...` or `"$U/scripts/tlc.sh" formal/tla/NAME.tla`, and the conformance test. Then run the verifier again.
   - **Done when** the verifier passes. If you changed the verifier after step 4, say so in the report, and run step 4 again on the changed verifier against the code without the new change.
6. **Run mutation testing on the changed functions.**

   ```bash
   "$U/scripts/mutate.sh"                     # the functions changed since HEAD
   "$U/scripts/mutate.sh" --base main         # the functions changed since main
   "$U/scripts/mutate.sh" wallet/core.py::withdraw
   ```

   Review each survivor. A survivor is harmless (the same behavior: an equivalent mutant, or a change only in the text of a message) or a real gap.
   - **Done when** each survivor has a test that kills it, or a reason why it is harmless.

Report the claim with its strength ([../references/verifiers.md](../references/verifiers.md#general-rules)), each verifier with its control result, and each agent-picked invariant.
