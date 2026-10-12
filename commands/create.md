# create

Generate a project-local verify skill with a feature map, and a Verifier section for each feature. This is the create-verification-skill model ([../references/adapted/create-verification-skill.md](../references/adapted/create-verification-skill.md)) with our preferences for what counts as a verifier. When the original skill is installed, the user can start it (it sets `disable-model-invocation`); then `create --spec` extends its feature files instead of writing a second skill.

Write the skill for the next agent: it reads it cold, mid-task, with no memory of the app. The shape is in [../references/verify-skill.md](../references/verify-skill.md).

## Steps

1. **Interview the repo, not the user.** Run `understando create`. It prints the surfaces it sees, the run commands, the existing verify skills, the feature candidates and the repo's own test commands (proposals only). Read the code for the rest: how a user reaches each feature, how an agent can drive it, what evidence it leaves, and whether two instances can run side by side. Ask the user only what you cannot observe. When the checkout does not start, fix that first or report it precisely.
   - **Done when** you can name the surface, the launch, the doctor check, the drive, the evidence and the cleanup from the code.
2. **Write the spec.** Write `create.spec.json` in the shape of [../references/verify-skill.md](../references/verify-skill.md): the six sections, the helper bodies, and the top 3 to 5 user-facing features. Give each feature its `surface` (frontend, backend, llm or other), its `paths`, the evidence files that a drive leaves, and one `control`: an anchor edit that plants a bug in the feature's code ([../references/controls.md](../references/controls.md)).
   - **Done when** no section and no feature field is a placeholder.
3. **Write the skill.** Run `understando create --spec create.spec.json`. It shows the files it writes and the branch. After the user's yes, run it again with `--yes`. It commits `.agents/skills/verify-<app>/` (SKILL.md, helpers/verify, features/README.md, one file per feature) and the relative link `.claude/skills/verify-<app>` on the branch `understando/verify-<app>`. `--patch FILE` writes a patch instead. Then run `understando create --check`.
   - **Done when** `create --check` prints `the shape holds.`
4. **Prove the skill on ONE feature.** Run `understando create --prove <feature>`, then with `--yes` after the user's yes. It runs the skill's own launch, doctor, drive and cleanup in a scratch copy of the branch, checks that the evidence is still in the run folder after the cleanup, and plants the feature's control: the drive must fail. Fix what fails (in the spec, then step 3 again); cleanup runs after each failed try too. A skill that never ran is a draft.
   - **Done when** it prints `PASS: the skill ran end to end, the evidence survived cleanup, and the control made the drive fail.`
5. **Fill the Verifier sections.** For each feature: `understando discover --feature F`, then `understando build` for its verifiers at the feature's bar, then `understando probe --feature F`. Then `understando create --verifier --yes` writes each Verifier section again from the store.
   - **Done when** each feature file names its surface, its bar, its invariants and the verifiers that meet the bar.
6. **Offer the upkeep loop.** Point the user at `understando maintain`.
