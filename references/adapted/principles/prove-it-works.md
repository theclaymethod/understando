<!--
adapted-from: skills/principle-prove-it-works/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: principle-prove-it-works
-->
# Prove it works

Verify every task output by checking the real thing directly. Do not infer from proxies, self-reports, or "it compiles".

**Why.** Unverified work has unknown correctness. Indirect checks (file mtimes, output freshness, agent self-reports, cached screenshots) feel cheaper than direct observation. Acting on a wrong inference costs far more than checking the source.

- Check process liveness directly, not through derived state.
- Read the actual value, not a cached or derived representation.
- When verification fails, suspect the observation method before suspecting the system.

**Script the check when you can.** The strongest proof is a deterministic script that reruns the same comparison. Write it, run it, and keep its output as an artifact a reviewer can rerun instead of trusting your word. Keep the artifact visible to the human. Commit it only for large or complex work where the trail must stay auditable.

Done when: the check ran against the real artifact and its output is attached.

**Where understando applies it.** `probe` (planted-bug controls prove the check can fail) and `trim` (confirm the e2e test covers the behavior before deleting a unit test).
