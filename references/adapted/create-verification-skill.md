<!--
adapted-from: skills/create-verification-skill/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: create-verification-skill
-->
# Create a verification skill

Every serious project needs a scripted way to drive the real app and prove behaviour: launch it, exercise a feature the way a user does, and capture evidence. The output is a project-local skill, written for the next agent, which reads it cold. `understando create` is this playbook, with a Verifier section for each feature ([../verify-skill.md](../verify-skill.md)).

1. **Interview the repo, not the user.** Answer from the code: the surface that a user touches (web UI, CLI, TUI, desktop, API, mobile, library; pick the primary one), how the app runs locally (the repo's own dev command, ports, env, seed data, auth), how an agent can drive it (existing harnesses first, then browser/CDP, a PTY harness or plain HTTP), what evidence it can capture, and whether two instances can run side by side. Ask the user only what you cannot observe. When the checkout does not start, fix that first or report it precisely; a missing asset that blocks startup may be created as marked scaffolding and removed in cleanup.
2. **Generate the skill.** SKILL.md with frontmatter (name and a description that names the app, the surface and when to use it) and these sections, each grounded in what the interview found: **Launch** (the exact command, how to tell it is ready, the teardown; for a short-lived CLI, build once and drive each run in its own session), **Doctor** (one read-only check: is this instance worth driving?), **Drive** (the real selectors and commands of this repo; stable handles over coordinates), **Evidence** (the proof standards: the real user path, the action and the resulting state, the side effects, mocks only at a real boundary, observe what a dry-run skips), **Cleanup** (kill only what the run started; keep the evidence at a named place), **Helpers** (each script executable, its invocation in the body).
3. **Seed the feature map.** features/README.md and one file for each of the top 3 to 5 user-facing features. Each file answers from the user's point of view: what the feature is, how to reach it, how to drive it, and what end state proves it. The four H2s are `Sub-features`, `How to get to it (user POV)`, `Driving it with <harness>` and `Gotchas`. understando adds a fifth, `Verifier`.
4. **Prove the skill before you hand it over.** Run its own instructions end to end once: launch, doctor, drive ONE feature, capture the evidence, clean up. After the cleanup, confirm that the evidence still exists at the named place. Run the cleanup after each failed try too. understando adds one check: the feature's control must make the drive fail. A skill that never ran is a draft.
5. **Offer the maintenance loop** ([maintain-verification-skill.md](maintain-verification-skill.md)).
