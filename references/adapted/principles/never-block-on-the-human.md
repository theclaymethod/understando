<!--
adapted-from: skills/principle-never-block-on-the-human/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: principle-never-block-on-the-human
-->
# Never block on the human

The human supervises asynchronously. Stay unblocked. Make reasonable decisions, proceed, and let the human course-correct after the fact.

**Why.** Every permission pause stalls the pipeline and makes the human the bottleneck. Code changes are reversible and reviewable, so a wrong decision usually costs less than blocking.

- **Proceed, then present.** Do the work and show the result. Do not ask "should I do X?". Do X and explain why.
- **Make the system self-healing.** When you notice a problem, log it and fix it in the next round.

**Boundaries.**

- Irreversible actions (force-push, delete production data, send external messages) still need confirmation.
- Reversible actions (write code, edit notes, split tasks) proceed without blocking.
- Product direction comes from the human. Execution does not block.

**Exception for understando.** Invariants, claim wording and waivers are the user's call. These steps stop for the user and never proceed on a default:

- `understando discover` (the invariants and the edge-case questions).
- `close` when it offers reword or waive for an open claim.
- Any change to the wording of a claim.

Everything else proceeds.

Done when: no reversible step waited on the human, and every discover, reword and waive decision came from the user.

**Where understando applies it.** every verb except the exceptions below (understando proceeds on reversible work and presents the result).
