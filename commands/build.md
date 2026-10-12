# build

Verifier-driven development for new work on a feature. [The rules for every verb](../SKILL.md#rules-for-every-verb) apply. Run `understando build --feature F` at any time: it prints each step and whether its criterion holds. For the general loop, use the tdd skill when it is installed, else [../references/adapted/tdd-red-first.md](../references/adapted/tdd-red-first.md) and [../references/adapted/feature-playbook.md](../references/adapted/feature-playbook.md).

The checks run at a commit in a scratch copy of the repo: commit the check, then the code.

## Steps

1. **Invariant.** The user states it: [discover.md](discover.md).
   - **Done when** the feature has an invariant with `author: user`.
2. **Pick the check.** Run `understando build claim --invariant I1 [--risky]`. It writes the claim and names the strongest practical check on the ladder for the feature's bar: e2e < property < types/contracts < TLA+ < Lean with conformance ([../references/evidence-bars.md](../references/evidence-bars.md)). A risky backend invariant goes to `formalize`.
   - **Done when** each claim has a plan.
3. **Write the check.** Write the test, the contract or the spec. Then `understando build check --claim C1 --kind KIND --command "..." [--code PATH::SYMBOL] [--cc-id ID]`. For frontend, `--evidence '*.webm,*.png'`; for llm, `--score RE --frozen JUDGE`.
   - **Done when** each claim has a check with a command.
4. **Prove that it fails.** `understando build red --check V1` with one of: `--at HEAD` (the check comes before the code), `--stub PATH@REF` (the file as it was before the feature), or `--plant EDIT_JSON` (a planted bug, [../references/controls.md](../references/controls.md)). A stub or a planted bug becomes a control of the check.
   - **Done when** each check went red. A check that stays green cannot prove the code: make it test the behaviour that the code must add.
5. **Write the code.** Write the code until the check passes, commit it, then `understando build green --check V1`.
   - **Done when** each check is green at the head.
6. **Probe.** `understando probe --feature F`, and `understando probe mutate --feature F` for the riskiest code.
   - **Done when** each check is proven, each claim meets its bar, and `build --feature F` prints `DONE`.
