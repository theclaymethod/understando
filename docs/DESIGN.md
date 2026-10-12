# understando: design

Agreed with Clayton on 2026-10-11, when understando was cut down to its core (the tag `pre-strip` holds the review tool before the cut).

## Purpose

Verifier-driven development and formal verification. A check counts only when a planted bug makes it fail. understando helps an agent and a user:

- state the invariants of a feature (the user's call, through edge-case questions);
- write the strongest practical check for each one, at the bar of the feature's surface;
- prove that each check fails on a planted bug, a stub or a mutant before it counts;
- lift a risky backend invariant to a TLA+ model check or a Lean proof with conformance against the real code;
- keep it honest as the code changes;
- hand an explainer the data and the code references, for visual-explainer to render.

## The model: a verify skill with our bar

The core artefact is a project-local verify skill with a feature map, in the shape of pstack's create-verification-skill: `.agents/skills/verify-<app>/` (SKILL.md with Launch, Doctor, Drive, Evidence, Cleanup and Helpers; `helpers/verify`; `features/README.md` and one file per feature), with a relative symlink from `.claude/skills/`. understando's difference is the **Verifier** section of each feature file: the surface, the bar, and the verifiers that meet it ([evidence-bars.md](../references/evidence-bars.md)).

- **Frontend:** a real-browser e2e of the user path, with a recorded video and screenshots.
- **Backend:** Formal (Lean or TLA+ with conformance) for a risky invariant; Code Contracts (a `@cc` contract with a check that a control proves); types, import rules and property tests for wiring.
- **llm:** a recorded eval with a frozen judge or labels, and a degraded variant that must score worse.

Every verifier has a control. A verifier that cannot fail does not count. An invariant that the agent picked is marked `author: agent`, and its claim stays Backed until the user accepts it.

The skill is the one place where understando writes into a repo: a commit on `understando/verify-<app>`, or a patch, after the user's yes. A repo with a verify skill already gets it extended, not duplicated.

## Verbs

| Verb | Job |
|---|---|
| `create` | Interview the repo, write the skill and the feature map, prove it end to end on one feature (the drive, the evidence after cleanup, the control fails). |
| `discover` | The user states the invariants of a feature. |
| `build` | The verifier-first loop: invariant, the check the bar asks for, red on a planted bug or a stub, the code, green, probe. |
| `probe` | Run the controls; `probe mutate` runs mutmut (fast default) and cosmic-ray (targeted on the riskiest changed lines), with equivalent-mutant filters, per-test coverage and a kill matrix. |
| `formalize` | The proof tier: the 7-check conformance, proof receipts (hashes, axioms), the drift stamp, the sync into the store, and `--recheck`. |
| `maintain` | The upkeep pass of maintain-verification-skill: a source brief and a live drive for each feature, the controls again, the stale verifiers flagged; at most one change set. |
| `snippet`, `export` | Code refs (symbol anchors, ready-head resolution, permalinks, diff line marks, the no-hand-copy guard), and the data for visual-explainer. |
| `doctor`, `setup` | What is present; the install. |

## The evidence store

One JSON file for each verify skill, `~/.understando/runs/<repo>/<app>/verify.json` ([schema/verify.schema.json](../schema/verify.schema.json)): the features, the invariants with their author, the claims with their parts, the checks with their commands and last results, the controls with their results, and the mutation runs. Code refs are anchors, never pasted code. The strengths are derived (`scripts/strength.py`): a part is as strong as its strongest check that caught its bug, and a claim is as strong as its weakest part. Run state is local and never in a git repo.

## Running commands

There is no stored CI profile. A verb runs the command that the user names, or the repo's own test command (AGENTS.md, the workflows), and it shows the commands once and runs them only with `--yes`, on each invocation. Every run is in a scratch worktree of a private clone; the user's checkout and branches do not change.

## Tests

End to end only, never unit tests. `tests/e2e.sh` drives the kept loop on the fixture repo (`tests/fixture`), and `tests/formal/e2e.sh` takes the fixture's Lean and TLA+ examples to Formal, syncs them into the store and rechecks them. `tests/isolate.sh` and `scripts/testguard.py` keep each test out of the real `~/.understando`.
