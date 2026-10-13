# build: verifier-first work on a behavior

Write the verifier before the code, and prove that it can fail. What counts for each surface is in [../references/verifiers.md](../references/verifiers.md). Proofs are in [../references/formal.md](../references/formal.md). When the tdd skill is installed, use it for the red-green rhythm; the steps here set the bar.

## The gate

`scripts/gate.sh` keeps one state for each repo. While this skill is active, a hook denies a write to a source file until the state is open. The hook allows tests, specs, fixtures, `formal/`, `*.lean`, `*.tla`, `*.cfg`, `*.md` and verify skills at any time, and any file outside the repo. For a layout with other verifier folders, run `gate.sh allow 'GLOB'`. The state expires after 12 hours.

```text
start "<invariant>"  →  write the verifier  →  red -- <command>  →  write the code  →  green -- <command>
   (closed)               (edits allowed)         (opens the gate)                      (records the pass)
```

If an edit is denied, do the next step of the list. Do not look for another way to write the file. The gate is off only when the user said to skip verifier-first: ask the user, then run `gate.sh off "<reason>"`.

Codex has no hooks in a skill. Add `"$U/scripts/gate.sh" hook` as a `PreToolUse` command for `apply_patch` and `Bash` in `~/.codex/hooks.json`, and check with a test edit that Codex denies it. Without a hook, follow the steps by hand: no source edit before `gate.sh red` succeeds.

## Steps

1. **Ask the user for the invariant.** Ask edge-case questions, one behavior at a time: a boundary input, an odd order of events, a failure part-way through ("what should happen if the amount equals the balance?"). Give no suggested answer. Then run:

   ```bash
   "$U/scripts/gate.sh" start "<the invariant in the user's words>"
   ```

   - **Done when** the user's answers state the invariant and the gate is closed. An invariant that you pick is marked agent-picked, and its claim stays at Backed or lower until the user accepts it.
2. **Choose the verifier.** Take the strongest practical verifier for the surface. A risky backend invariant gets a proof (Lean, TLA+) or a Code Contract with a check.
   - **Done when** you can name the verifier, its tool, its command and its control.
3. **Write the verifier.** Write the e2e or integration test, the property test, the contract or the model, in the working tree, next to the code that it tests. The gate allows these files.
   - **Done when** one command runs it.
4. **Prove that it fails, and open the gate.** Show the command, then run it after the user says yes. For new behavior, the verifier fails on the code that you have:

   ```bash
   "$U/scripts/gate.sh" red -- <the verifier command>
   ```

   For a behavior that exists already, plant a bug in a throwaway copy (the arguments are those of `control.sh`):

   ```bash
   "$U/scripts/gate.sh" red --control --replace PATH 'GUARD TEXT' 'BROKEN TEXT' -- <the verifier command>
   "$U/scripts/gate.sh" red --control --patch stub.diff -- <the verifier command>      # a stub, or a deleted guard
   ```

   - **Done when** `gate.sh` prints `red` and the failure names the behavior, not a typo or a missing import. A verifier that passes before the code exists is `not red`: make it test the behavior that the code must add.
5. **Write the code.** For a proof, run `"$U/scripts/lean-check.sh" --dir formal/lean --import MODULE THEOREM...` or `"$U/scripts/tlc.sh" formal/tla/NAME.tla`, and the conformance test. Then run:

   ```bash
   "$U/scripts/gate.sh" green -- <the verifier command>
   ```

   - **Done when** `gate.sh` prints `green`. If it prints the note that a verifier file changed after it went red, say so in the report, and run red again on the changed verifier against the code without the new change.
6. **Run mutation testing on the changed functions.**

   ```bash
   "$U/scripts/mutate.sh"                     # the functions changed since HEAD
   "$U/scripts/mutate.sh" --base main         # the functions changed since main
   "$U/scripts/mutate.sh" wallet/core.py::withdraw
   ```

   Review each survivor. A survivor is harmless (the same behavior: an equivalent mutant, or a change only in the text of a message) or a real gap.
   - **Done when** each survivor has a test that kills it, or a reason why it is harmless.

Report the claim with its strength ([../references/verifiers.md](../references/verifiers.md#general-rules)), each verifier with its control result, and each agent-picked invariant. `gate.sh status` prints the invariant and the red and green records.
