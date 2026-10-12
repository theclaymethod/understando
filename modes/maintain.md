# maintain: keep the verify skill honest

A feature map goes stale when the app changes. When pstack's maintain-verification-skill is installed, the user can start it with `/maintain-verification-skill`; then do step 5 here. Else do all the steps.

Edit only the verify skill's own folder (SKILL.md, features/, its helpers). A behavior that the map describes and the app no longer has is doc drift (fix the map) or a product gap (report it to the user).

1. **Find the target.** Find the project-local verify skill (`.agents/skills/verify-*/` or `.cursor/skills/verify-*/`). Several: ask which one. None: point at [create.md](create.md).
   - **Done when** you have one target.
2. **Fix the index.** Compare `features/README.md` with the feature files: fix missing, extra, duplicate and dead entries.
   - **Done when** each entry has a file and each file has an entry.
3. **Read each feature from source.** Run one read-only subagent for each feature file, at the same time. Each one explains how the feature works from source, cites likely drift, and returns one live recipe. Subagents never drive the app and never edit files.
   - **Done when** each feature has a returned summary.
4. **Drive each feature live.** Doctor first, then drive each feature at least once; doctor again after any failed drive. The evidence survives every cleanup. Fix doc drift and harness gaps, and drive each fix again.
   - **Done when** each feature was driven, or is unreachable with the exact prerequisite and the route that you tried.
5. **Run each control again.** For each verifier in each Verifier section, run its control with `"$U/scripts/control.sh"`, as written in the section.
   - **Done when** each control went `red`. Flag each verifier whose control now stays `green`: it does not count now. Mark it under "Verifiers that do not count".
6. **Report.** Say the outcome: `clean` (nothing to change), `changed` (the proven corrections, in the working tree) or `blocked` (what blocked it). List each flagged verifier and each product gap.
   - **Done when** the user has the outcome and the coverage.
