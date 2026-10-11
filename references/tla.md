# Tier 4: TLA+ model of a loop, a retry or a state machine

Use when the claim is about **order and stopping**: a loop's stop rules, retries, a state machine, or concurrency. TLC explores every behaviour of a small model. A trace replay connects the model to the real code.

## Spec

- One `<Name>.tla` and one `<Name>.cfg` per model, in `<project>/formal/tla/`.
- Variables: the loop's control state (a phase, a round counter, a flag for each early exit), and a **history** variable that records each environment choice (each editor outcome, each check result). The history makes each terminal state one whole behaviour, so it is also the test vector.
- The environment's choices are `\E x \in Choices : Step(x)`. Keep each choice set small and finite: the cases that change a decision, not every value.
- Transcribe the code's guards in the code's order. A `for ... in range(n)` is a counter with a `< n` guard. A `break` sets the phase to `"done"` with a recorded reason.
- Give the terminal state an explicit stutter: `Done == phase = "done" /\ UNCHANGED vars`. Then TLC's deadlock check stays on, and a real deadlock (a stuck state that is not done) is reported. Pass `--no-deadlock-check` (TLC `-deadlock`) only for a spec without terminal states, and say why.

## Properties

- `TypeOK`: the type invariant.
- Safety invariants: the claims (a bound, a guard that must hold, a thing that must never happen after a lost call).
- Liveness: `Termination == <>(phase = "done")` with `Spec == Init /\ [][Next]_vars /\ WF_vars(Next)`.
- A claim that is an implication over a step ("after a round that ..., the loop stops") is easiest as an invariant over a history entry: the last entry has the property, so the phase is done.

Run `formal_tlc.py check --spec <Name>.tla --cfg <Name>.cfg`. It prints the status, the violation and the parsed trace.

## Control

`formal_tlc.py control --spec <Name>.tla --cfg <Name>.cfg --symbol <Definition> --match '<guard>' --op delete-line --pattern <Invariant>` (an anchor edit: `--op replace-with --with '<text>'` rewrites the match; the symbol is a `<Name> ==` definition; never type the spec text again). TLC must report a violation of that invariant, with a trace. A planted spec that stays green means that the property does not read that guard.

## Conformance: trace replay

1. Write a second cfg (`<Name>Vectors.cfg`) with small constants and only `TypeOK`.
2. `formal_tlc.py vectors --spec <Name>.tla --cfg <Name>Vectors.cfg --done 'phase="done"' --out <name>_vectors.json`. Each vector is one terminal state with its history and its decisions. The file holds the spec hash, the cfg hash and the constants. Use `--check` in CI.
3. A test drives the **real** loop with scripted collaborators: each history entry tells the fake editor or fake check what to return. It compares the observable decisions (which rounds ran, which were kept, why the loop stopped, the final outcome) with the vector.
4. A counterexample trace from step 4 of formalize is a vector too: replay it on the real code. Red there makes the blocker code-first.
5. Code control: plant the defect in the real loop (`formal_run.py --copy ... --edit ... --expect red`). The replay must go red.

## The 7-check pass for a loop

| Check | Question |
|---|---|
| statement_parity | Does each property say what the claim says, with the same scope (which rounds, which stop reasons)? |
| state_parity | Does each variable map to a code variable or a recorded decision? |
| transition_parity | Does each action map to one branch of the loop body, in the same order? |
| concurrency_parity | Is the code sequential (awaits in one task)? Then say so. Otherwise, model each interleaving point. |
| cancel_drain_parity | Lost calls, timeouts and partial edits: is each early exit modelled? |
| runtime_evidence | Do all terminal states replay green on the real code? |
| drift_gate | Spec hash, cfg hash, commit and blob of the mapped code, stamped. |

## Artifact record

`formal_record.py build --kind tla --tier 4` with the TLC check, the replay run, the spec control and the code control; then `stamp --code <py files> --model <tla> <cfg> <vectors>`.
