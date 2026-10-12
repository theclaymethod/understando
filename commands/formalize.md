# formalize

The backend proof tier. Lift a claim of a backend feature up the verification ladder and prove that its verifier can fail. One claim area at a time is one **frog**. The loop runs a frog to an artifact record, then picks the next frog. It is the Python adaptation of lean-formal-feedback-loop.

The ladder is in [../references/verdicts.md](../references/verdicts.md). This command builds rungs 2, 4 and 5.

## Before you start

[The rules for every verb](../SKILL.md#rules-for-every-verb) apply. Run `understando formalize --claim C1` first: it names the rung and the route, and it says when the invariant of the claim is agent-picked (then the record reaches at most "Formal (pending user confirmation)"). When the skill lean-formal-feedback-loop is installed (`understando doctor` names it), use it for rung 5. When a proof shows that the code is wrong, fix the code first ([fix-root-causes](../references/adapted/principles/fix-root-causes.md)), or ask whether the claim is the right one ([attack-the-premise](../references/adapted/principles/attack-the-premise.md)).

After step 9, run `understando formalize --sidecar $R/formal/verifiers.json`. It takes the user's invariant decisions from the store into each record, rates each record again, and writes each record into the store as checks with their controls: one check for each property (`formal_record.py build --property NAME=CLAIM[=CHECK NAME]`, and `--control ...:PROPERTY`). The sync keeps the IDs and the names of the checks, matches the proposed claims by key, gives a control a fresh ID when another check holds its ID, and is idempotent.

When the code or the model changes (`formal_record.py drift` is red, or `understando doctor` says the proof is older than its code), run `understando formalize --recheck F01`. It runs the record's check, conformance run and controls again (each result keeps the helper call that made it), stamps the drift block at the repo HEAD, rates the record again and syncs it.

## The helpers

Set `U` to the understando directory. The helpers are stdlib Python: `$U/scripts/formal_lean.py`, `formal_tlc.py`, `formal_run.py`, `formal_witness.py`, `formal_record.py`. Each one prints JSON and documents itself in `--help`. Toolchains: `lake` (elan), `java` and `~/.understando/tools/tla2tools.jar` (override with `UNDERSTANDO_JAVA`, `UNDERSTANDO_TLA2TOOLS`). understando finds java at `$JAVA_HOME/bin/java` or Homebrew's `/opt/homebrew/opt/openjdk/bin/java` without a PATH edit, and passes that path to TLC.

Inputs: the claims of the store, the repo at its head, and the understando branch for the artifacts. Specs, Lean projects and conformance tests go on that branch, for example under `<project>/formal/` and `<project>/tests/`. They never go into the user's own commits.

## The Formal verdict

**Formal** needs all of these. `formal_record.py verdict` checks each one and lists the ones that are missing:

- a tier 4 or 5 check is green: `lake build` passes, with no `sorry`, `admit` or new `axiom`, and `#print axioms` lists only `propext`, `Quot.sound` and `Classical.choice`; or TLC finishes with no error, with its deadlock check on;
- a conformance run against the real code is green, and the 7-check pass is complete;
- each control is red: a planted wrong model or spec breaks the proof or the model check; for tier 5, a planted wrong function also breaks conformance;
- the drift block is stamped;
- the invariant is **user-confirmed**: an invariant with `author: user` and `status: accepted` in the store, from `discover`. An invariant that you wrote is a proposal. A record with a proposed invariant gets at most `Formal (pending user confirmation)`. `formalize --sidecar` takes the decision from the store; by hand, record `--invariant-author user --invariant-ref <invariant id>` only after the user confirms the wording.

## Steps

1. **Rank frogs.** For each candidate claim, score `EV = (Impact * BugPrior * Reach) / (ProofCost * ModelCost)`, each 1-5. Raise BugPrior with history: `git log --oneline -S '<symbol>' -- <file>` and `git log --oneline -20 -- <file>` in the repo (fix commits, reverts, churn). Pick the shape: a pure rule goes to tier 5, a loop, retry, state machine or concurrency goes to tier 4, and a rule with a large input space and no cheap model goes to tier 2.
   - **Done when** each candidate has an EV with its five scores and a target tier, and you work only the top frog.
2. **Fill the reverse-round card.** Surface (file and function), failure class, math (the theorem family or the TLA+ properties), and artifact (what proves it: theorem names, spec, vectors, test). State each invariant as one plain sentence, mark it proposed, and add 1-3 edge-case questions for the user ("what should happen if ..."), with no answer.
   - **Done when** all four card fields and each proposed invariant with its questions are written down.
3. **Model.** Transcribe the code, not the intent: same guards, same order, same early returns. Write each abstraction that you make as a comment beside it. Tier 5: [references/lean-python.md](../references/lean-python.md). Tier 4: [references/tla.md](../references/tla.md). Tier 2: [references/property.md](../references/property.md).
   - **Done when** each branch of the mapped code has a counterpart in the model, or a comment says why not.
4. **Prove or check, up to the first hard blocker.** Run `formal_lean.py check` or `formal_tlc.py check`. A failed tactic, a refuted `decide`, or a TLC violation is a blocker. Proof friction is evidence: it is a signal about the code before it is a tactic problem.
   - **Done when** the check is green, or you have the first hard blocker and its exact output.
5. **Route the blocker.** Pick exactly one route: `code-first` (the code is wrong), `model-first` (the model does not match the code), `harness-first` (the tests, vectors or mappings are stale) or `theorem-first` (the claim is too strong or mis-scoped). Under uncertainty, pick code-first: a code bug that you call a model issue costs the most. Change one thing, then run step 4 again. After two failed iterations, split the theorem and route each part.
   - **Done when** the route is recorded with its reason, and the check is green or the blocker is open with a witness.
6. **Extract a witness.** For a refuted statement, search the model for the smallest counterexample (a Lean `witness` function, or the TLC trace) and run `formal_witness.py test` to write a regression test that calls the real function. Run it. A code-first witness test must fail on the code at the head.
   - **Done when** each open blocker has a witness input and a test whose status you ran and recorded.
7. **Run the 7-check conformance pass.** Statement, state, transition, concurrency, cancel/drain, runtime evidence and drift parity (the table is in [references/lean-python.md](../references/lean-python.md)). Runtime evidence is a conformance test that feeds the same inputs to the model and the real code and compares the observable decisions: Lean vectors plus a live oracle, or TLC terminal states replayed. Run it with `formal_run.py`.
   - **Done when** each check reads `pass` or `n/a` with a note, and the conformance run is green.
8. **Run the controls.** Model control: `formal_lean.py control` or `formal_tlc.py control` with one planted defect (a guard removed, a bound moved). Code control: `formal_run.py --copy ... --edit ... --expect red` on the real function. A control that stays green means that the verifier cannot fail there. Report it as the most important finding.
   - **Done when** each control has a result, and each one is red or is reported as cannot-fail.
9. **Emit the artifact record.** `formal_record.py build`, then `stamp` (the commit and blob of the mapped code, the hash of each model file), then `add` to the sidecar `$R/formal/verifiers.json`. Run `formal_record.py drift` before you reuse a record: a red drift gate makes the record stale.
   - **Done when** the record is in the sidecar and `formal_record.py verdict` prints its verdict.

Recompute the frog ranking and start again at step 1, or stop.

## Report

- Each frog: its invariants (proposed or confirmed), the theorems or properties, the verdict, the route, the control results and the conformance result.
- A blocker routed code-first is a **bug in the code**. Report it first, in the finding format of [../references/adapted/find-bugs.md](../references/adapted/find-bugs.md). The heading is `P1 — [Small fix, 95% finding confidence, 90% fix confidence] <one line>`. Then give the trigger (the witness input), expected and actual, the impact, the fix direction and the evidence. The evidence is the failing witness test and the command that runs it. Do not fix the code. The witness test goes on the understando branch, or to the author as a patch. Keep a refutation that has no witness run apart, as a lead.
- Each proposed invariant, for the interview with the user: the plain sentence, the edge-case questions, what the code does today in each case (file:line), and whether that looks intended or like a bug.

## Sidecar

`$R/formal/verifiers.json`: `schema` (`understando.formal/1`), `repo`, `app`, `head`, `proposed_claims` [{`id`, `text`, `source`, `claim`}] for claims that the store does not hold, and `verifiers`, one artifact record each: `id`, `kind` (lean, tla, property), `ladder_tier` (2, 4, 5), `claims`, `description`, `card`, `check`, `conformance` {`result`, `checks`}, `controls` [{`id`, `target` (model, code), `result`, `property`, `map_id`}], `properties` [{`name`, `part`, `check_name`, `check`, `controls`}], `route`, `blocker_open`, `invariant` {`author`, `ref`, `status`, `items`}, `witness`, `witness_test`, `drift` {`commit`, `root`, `code_files`, `model_files`}, `formal` {`verdict`, `missing`}, `independence`, `cost`. scripts/formal_sync.py owns how these merge into the store.

Run only the formal helpers and the test command that the user named, under [the rules for every verb](../SKILL.md#rules-for-every-verb). No model calls.
