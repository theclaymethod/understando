# maintain

The upkeep loop of the verify skill, modelled on maintain-verification-skill ([../references/adapted/maintain-verification-skill.md](../references/adapted/maintain-verification-skill.md)). The unit of rigour is the feature. [The rules for every verb](../SKILL.md#rules-for-every-verb) apply.

## Edit scope

Edit only the verify skill folder (SKILL.md, features/, helpers/). Never edit product code in this pass: a behaviour that the map describes and the app no longer has is doc drift (fix the map) or a product gap (report it).

## Steps

1. **Run the pass.** `understando maintain [--feature F]` shows the commands and writes one source brief for each feature to `$R/maintain/`. Run one read-only subagent for each brief, at the same time ([../references/adapted/subagents.md](../references/adapted/subagents.md)). The subagents never drive the app and never edit a file.
   - **Done when** each feature has a returned summary: the feature, its source entry points, the drift or `none`, one live recipe.
2. **The live pass.** After the user's yes, `understando --yes maintain`. For each feature it runs the drive (launch, doctor, drive, cleanup) and every check against the current code, with the skill from the understando branch, then every control again. Evidence stays in the run folder.
   - **Done when** it prints the outcome: `clean`, `changed` or `blocked`.
3. **Triage.** Each `FLAG` names a verifier: `STALE` (its control no longer makes it fail, so it does not count now), `FAILING` (a product gap, or drift of the skill), `STALE-ANCHOR` (a control that no longer resolves), `PROOF-DRIFT` (`understando formalize --recheck`), `INDEX` (the feature map). Wrong description: fix the map. A behaviour that the harness cannot drive: fix the harness. Broken app behaviour: record it for the user.
   - **Done when** each flag has a fix or a report.
4. **Ship or stop.** For `changed`: at most ONE change set of proven corrections on the understando branch. Re-drive each fix, then `understando create --spec FILE --yes` (or `create --verifier --yes`). For `clean` or `blocked`: no change set; report the outcome and the coverage.
