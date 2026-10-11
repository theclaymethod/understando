# ready

Run map, probe, close, trim and explain, then print the four-gate checklist. The full run is for the user to start. `understando ready --report` only reads and computes the gates, so you may run it.

Each stop of this playbook ends with one question to the user. Ask it as [Asking the user](../references/working-rules.md#asking-the-user) tells you: the situation, a Next line, and numbered options.

The gates:
1. **verified:** each claim is Formal, Proven or Backed, or the user waived it.
2. **no excess code:** trim found nothing that can go, and the user decided each "excess or untested" item.
3. **no doubles:** no unit test repeats an e2e test.
4. **explainable:** the explainer builds (the glossary and the level rules), and each claim is in one promise. The STE lint of the PR section has 0 hard violations.

## Steps

1. **Run.** `understando ready --report`, or, when the user asks, `understando ready [--answers <close answers>]`.
   - **Done when** the four gate lines print. The checklist goes to `ready.json`, and `explain` puts it at the top of the explainer and of `pr-section.md`.
2. **Independent review.** The checklist names the review route: an installed interrogate, nemesis-review or code-review skill. Else a model of a different family runs [../references/adapted/code-review.md](../references/adapted/code-review.md) in a fresh context. The user starts it.
   - **Done when** the user has the route.
3. **Cold read (optional, paid).** With `--cold-read`, the checklist names a cold read of the explainer by a model of a different family. Show the cost and wait for a clear yes.
   - **Done when** the user said yes or no.

The verification parts of opening and shipping a PR are in [../references/adapted/pr-verification.md](../references/adapted/pr-verification.md).
