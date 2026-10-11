# build

The verifier-first playbook for new work. Start it only on an explicit request from the user. Run `understando build` at any time: it prints each step and whether its completion criterion holds. For the general feature workflow, use Poteto Mode's Feature playbook or the tdd skill when `understando routes` shows them, else [../references/adapted/feature-playbook.md](../references/adapted/feature-playbook.md) and [../references/adapted/tdd-red-first.md](../references/adapted/tdd-red-first.md).

Each stop of this playbook ends with one question to the user. Ask it as [Asking the user](../references/working-rules.md#asking-the-user) tells you: the situation, a Next line, and numbered options.

## Steps

1. **discover.** Find the invariants with the user ([discover.md](discover.md)).
   - **Done when** `understando discover status` prints `DONE`.
2. **The contract.** Write each confirmed invariant as a `@cc` contract (the code-contracts skill, or by hand). Then run `understando build claim --invariant I01 --cc-id <id> [--tier N] [--promise P1]`. It refuses an unconfirmed invariant.
   - **Done when** each claim has a `cc_id` and a confirmed invariant.
3. **The verifier, red first.** Write the verifier at the strongest practical tier. Run `understando build verifier --claim C01 --spec <file>`, then `understando build red-first --verifier V01 --at <stub commit>`.
   - **Done when** each claim has a verifier that went red before the code existed.
4. **The code.** Write the code until each verifier is green at the head.
   - **Done when** each verifier has a green baseline.
5. **probe.** Run `understando probe`.
   - **Done when** each verifier with a command is `proven`.
6. **The gates.** Run `understando ready`.
   - **Done when** the four gates pass.
7. **explain.** Run `understando explain`.
   - **Done when** the explainer exists for the head.
