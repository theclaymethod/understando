# ready

Run map, probe, close, trim and explain, then print the four-gate checklist. The full run is for the user to start. `understando ready --report` only reads and computes the gates, so you may run it.

Gate 1 needs each risky claim at its evidence bar, and each other claim at its bar or waived ([evidence-bars.md](../references/evidence-bars.md)).

Each stop of this playbook ends with one question to the user. Ask it as [Asking the user](../references/working-rules.md#asking-the-user) tells you: the situation, a Next line, and numbered options.

The gates:
1. **verified:** each claim is Formal, Proven or Backed, or the user waived it.
2. **no excess code:** trim found nothing that can go, and the user decided each "excess or untested" item.
3. **no doubles:** no unit test repeats an e2e test.
4. **explainable:** the explainer builds (the glossary and the level rules), and each claim is in one promise. The STE lint of the PR section has 0 hard violations.

## Steps

1. **Run.** `understando ready --report`, or, when the user asks, `understando ready [--answers <close answers>]`.
   - **Done when** the four gate lines print. The checklist goes to `ready.json`, and `explain` puts it at the top of the explainer and of `pr-section.md`.
2. **Independent review.** The checklist names the review route: an installed interrogate or nemesis-review skill. Else it names the autoreview fallback, [../references/adapted/autoreview.md](../references/adapted/autoreview.md). That is one reviewer in a fresh context, from another model family. It gets the goal, the promises, the diff and the trust map. It ranks each finding P0 to P3 with its file and line, in the finding format. Check each finding against the real code path: agreement is not proof. Record each finding as guess-tier evidence. When no fresh reviewer is available, report the gap: a self-review is never independent. Code review does not prove behaviour, so keep it apart from probe. The user starts the review.
   - **Done when** the user has the route, or the report says that no independent review was done.
3. **Cold read (optional, paid).** With `--cold-read`, the checklist names a cold read of the explainer by a model of a different family. Show the cost and wait for a clear yes.
   - **Done when** the user said yes or no.

The verification parts of opening and shipping a PR are in [../references/adapted/pr-verification.md](../references/adapted/pr-verification.md).
