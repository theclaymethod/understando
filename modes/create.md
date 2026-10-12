# create: a project-local verify skill

Write a verify skill that drives the real app the way a user does, with a feature map and a Verifier section for each feature. Write every file in the working tree, as ordinary uncommitted changes; the user commits them. The shape is in [../references/verify-skill.md](../references/verify-skill.md). What counts as a verifier is in [../references/verifiers.md](../references/verifiers.md).

When pstack's create-verification-skill is installed, the user can start it with `/create-verification-skill`. Then add the Verifier sections to its feature files, and do steps 3 and 4 here.

1. **Interview the repo, not the user.** Read the code for the surface (web UI, CLI, API, library), the launch command, the doctor check, the drive (an existing Playwright, `expect` or tester-army harness first; else a browser for web, a PTY for a CLI, HTTP for a service), the evidence, and whether two instances can run side by side. Ask the user only for what the code does not show. When the checkout does not build or start, fix that first or report it precisely.
   - **Done when** you can name the surface, launch, doctor, drive, evidence and cleanup from the code.
2. **Write the skill.** Write `.agents/skills/verify-<app>/SKILL.md` with its six sections, then link it:

   ```bash
   mkdir -p .claude/skills && ln -s ../../.agents/skills/verify-<app> .claude/skills/verify-<app>
   ```

   - **Done when** each section holds a real command or handle from this repo, and no placeholder.
3. **Seed the feature map.** Write `features/README.md` and one file for each of the top 3 to 5 user-facing features (from routes, commands, menus or docs). Give each feature its Verifier section: the surface, the bar, the invariants with their authors, and the verifiers with their controls.
   - **Done when** each feature file has the five sections, and each Verifier section names a control.
4. **Prove ONE feature end to end.** Run the skill's own launch, doctor, drive and cleanup. Check that the evidence is still at its place after cleanup. Then plant the feature's control and run the drive again:

   ```bash
   "$U/scripts/control.sh" --replace wallet/core.py 'if amount > balance:' 'if False:' -- <the drive command>
   ```

   Fix what fails, and run the cleanup after each failed try too. A skill that never ran is a draft.
   - **Done when** the drive passed, the evidence survived cleanup, and `control.sh` printed `red`.
5. **Offer maintain.** Tell the user that [maintain.md](maintain.md) keeps the map honest as the app changes.
   - **Done when** the user has the pointer.
