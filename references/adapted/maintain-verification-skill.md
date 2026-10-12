<!--
adapted-from: skills/maintain-verification-skill/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: maintain-verification-skill
-->
# Maintain a verification skill

A feature map rots when the app changes. This is the upkeep loop. The unit of rigour is the feature: cover each feature file from source, and exercise each feature live. `understando maintain` is this playbook, and it also runs the controls of every verifier again.

**Outcomes.** Pick one and say which: **clean** (each feature got source and live coverage; nothing to ship), **changed** (one change set of proven corrections), **blocked** (the pass could not finish; say what blocked it).

**Edit scope.** Edit only the skill's own folder. Never edit product code: a described behaviour that the app no longer has is doc drift (fix the map) or a product regression (report it).

0. **Locate the target**: the project-local skill with launch and drive sections and a feature map. None: point at create instead of inventing one.
1. **Index hygiene.** Fix missing, extra, duplicate or dead entries of the feature index.
2. **Source wave.** One read-only subagent for each feature file, at the same time. Each explains how the feature works from source, flags likely drift with citations, and returns one live recipe. Subagents never drive the app and never edit files.
3. **Reconcile.** Each feature file has a summary. Merge the recipes into few app states. Spot-check the cited drift. Look at recent churn for user-facing surfaces that the map lacks; name a source path before you call one missing.
4. **Live pass.** Required also when the source looks clean. The coordinator drives; follow the skill's own launch model. Hold three invariants: run doctor before the first drive, after each failed drive and on each fresh session; the evidence survives each cleanup, checked at its place; nothing a drive started outlives the drive. A doctor failure from skill drift: fix it under the edit scope and retry once. A feature that cannot be reached is `verified-unreachable` only with the concrete prerequisite and the route that you tried. Re-drive each harness fix before it ships.
5. **Triage.** Wrong or missing description: doc drift, fix it. Working behaviour that the harness cannot drive: a harness gap, fix it. Broken app behaviour: a product gap, record it for the user and keep it out of the change set. understando adds: a verifier whose control no longer makes it fail is stale, and it does not count until a control makes it fail again.
6. **Ship or stop.** Changed: one change set, after you read each changed file again. Clean or blocked: report the outcome and the coverage. Keep short run notes in a scratch place; do not commit them.
