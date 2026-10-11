# formalize

Climb a claim to tier 4 (a TLA+ model check) or tier 5 (a Lean proof with a conformance link). Start it only on an explicit request from the user. This file is the router stub. The sub-skills that do the work are in progress.

## Steps

1. **Check the intent.** Run `understando formalize --claim C01` or `--invariant I01`. It refuses a claim that the PR does not state and that links to no invariant from the user.
   - **Done when** it prints the target tier, or you report the refusal and route to `discover`.
2. **Route.** Tier 5: use the skill lean-formal-feedback-loop. Tier 4: use the TLA+ sub-skill when it exists. The toolchains are the user's to install: `understando signals` shows lean, lake, java, tla2tools and apalache.
   - **Done when** the proof or the model checks at the head.
3. **Record the verifier.** Add a verifier with `kind` lean or tla, `ladder` 5 or 4, and a `formal` block. The block holds the `tool`, the `artifact` and a `conformance` link (`status`, `source`). The link names a run that sends the same cases through the model and the code. Add a control that breaks the proof or the model.
   - **Done when** `understando map` rates the claim Formal. Without a passing conformance link the claim stays Backed.

When the proof shows that the code is wrong, fix the code first (fix-root-causes), or ask whether the claim is the right one (attack-the-premise).
