# trim

Gate 2 (no excess code) and gate 3 (no unit test that an e2e test already covers). Start it only on an explicit request from the user. Apply subtract-before-you-add and laziness-protocol.

Each stop of this playbook ends with one question to the user. Ask it as [Asking the user](../references/working-rules.md#asking-the-user) tells you: the situation, a Next line, and numbered options.

## Steps

1. **Report first.** Run `understando trim --report`. Gate 3: a unit test can go only when each control that turns it red also turns an e2e test red. Gate 2: a function that the e2e suite runs, and without which the suite stays green, can go. A function that no e2e test runs is "excess or untested".
   - **Done when** you showed the user the report.
2. **Add more candidates** when the user wants them. A dead-code tool, or a deletion pass by a model of a different family (guess tier), gives `[{"path", "name", "why", "source"}]` for `--candidates`.
   - **Done when** each candidate source that the user chose is in the report.
3. **Trim.** Run `understando trim`. It deletes on `understando/<pr>-ready` only. It moves each covered control to the e2e test that caught it, and runs the e2e suite again. It never deletes a `@cc` contract comment.
   - **Done when** it prints the deletions, and each unique unit test shows "convert to e2e first".
4. **Decide the rest with the user.** For each "excess or untested" item, the user keeps it, asks for a test, or deletes it. To keep it, run `understando trim --accept <path>:<name> --reason "<why>"`.
   - **Done when** gate 2 in `understando ready --report` passes, or the user stops.
5. **Clean up.** Run the cleanup skills that `understando routes` shows: simplify, ultra-clean, deslop or no-comments. Each keeps the `@cc` comments.
   - **Done when** the e2e suite is green at the new tip.
