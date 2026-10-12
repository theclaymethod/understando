# Formal: Lean, TLA+ and Code Contracts, with conformance to the real code

Use a proof for a risky backend invariant ([verifiers.md](verifiers.md)). Use Lean for a pure rule: the output depends only on the inputs. Use TLA+ for order and stopping: a loop, a retry, a state machine or concurrency. A proof counts only with conformance: the model and the real function agree on the same inputs. When the lean-formal-feedback-loop skill is installed, route to it for the loop below. It is written for Rust; the Python changes are in this file.

## Tools

`$U/scripts/setup.sh` installs these. The scripts find them for you.

| Tool | Path | Script |
|---|---|---|
| elan, `lean`, `lake` | on PATH, else `~/.understando/tools/elan/bin/` | `lean-check.sh` |
| Java | Homebrew openjdk (macOS `/usr/bin/java` is only a stub) | `tlc.sh` |
| TLC | `~/.understando/tools/tla2tools.jar` | `tlc.sh` |
| mutmut, pytest | `~/.understando/tools/mutation/bin/` | `mutate.sh` |

## The loop

Work one invariant at a time.

1. **Model.** Transcribe the code, not the intent: the same guards, in the same order, with the same early returns. A Python `int` is `Int`, a `Sequence` is a `List`. Write each abstraction as a comment beside it. A precondition that the code does not check becomes a hypothesis of the theorem; report it as a precondition, not as a proof.
2. **Prove or check, up to the first hard blocker.** A failed tactic, a refuted `decide` or a TLC violation is a blocker. Proof friction is evidence about the code before it is a tactic problem.
3. **Route the blocker.** Pick one route: code-first (the code is wrong), model-first (the model does not match the code), harness-first (the vectors or the tests are stale) or theorem-first (the claim is too strong). When unsure, pick code-first: a code bug that you call a model issue costs the most. Change one thing, then run step 2 again. After two failed tries, split the theorem.
4. **Keep the witness.** A counterexample (the smallest input from a Lean search, or the TLC trace) becomes a regression test that calls the real function. A code-first witness test fails on the current code. Report it to the user as a bug, and keep the fix for a separate step.

## Lean

```
formal/lean/
  lean-toolchain     the toolchain that setup.sh installed
  lakefile.toml      lean_lib <Name>; lean_exe vectors
  <Name>/<Rule>.lean the model and its theorems
  Vectors.lean       prints one JSON line per input with the model's output
```

```bash
"$U/scripts/lean-check.sh" --dir formal/lean --import <Name> <Ns.theorem>...   # build, axioms, no sorry
(cd formal/lean && lake exe vectors > <rule>_vectors.jsonl)                    # the conformance vectors
```

Prove with `unfold`, `split`, `simp`, `omega`, `decide` or induction. Try a bounded statement with `decide` first when the full proof is not obvious. Add `.lake/` to `.gitignore`.

**Conformance.** `Vectors.lean` writes an edge grid (each guard's boundary ±1) plus seeded pseudo-random inputs. A property test in the project's own test suite loads the vectors, calls the real function on each input, and compares the observable decisions: the return value, the raised error, the picked index. Compare only what a caller can observe. The test runs without Lean, so CI needs no Lean.

## TLA+

- One `<Name>.tla` and `<Name>.cfg` in `formal/tla/`. Model the control state and a history variable that records each environment choice. Then each terminal state is one whole behavior, and also a test vector.
- Keep each choice set small: the cases that change a decision.
- Give the terminal state an explicit stutter (`Done == phase = "done" /\ UNCHANGED vars`), so the deadlock check stays on.
- Properties: `TypeOK`, the safety invariants of the claim, and `Termination == <>(phase = "done")` with `WF_vars(Next)`.

```bash
"$U/scripts/tlc.sh" formal/tla/<Name>.tla                         # exit 0: no error
"$U/scripts/tlc.sh" formal/tla/<Name>.tla <Name>Vectors.cfg -- -dump states.txt
```

**Conformance.** TLC explores the model. Replay the counterexample trace, or each terminal state of a small second cfg, through the real code: scripted collaborators return what the history says, and the test compares the decisions (which rounds ran, why the loop stopped, the result).

## Code Contracts

Route to the code-contracts skill when it is installed. A `@cc` contract in the docstring states the invariant. `npx --yes @spolu/cc-check format` checks only its syntax, so back each contract with a check (an e2e, an integration or a property test) that runs the rule, and give that check a control. The contract states the invariant; the check with its control proves it.

## Controls

- A planted wrong model (a guard removed, a bound moved) must break `lean-check.sh` on a theorem, or make `tlc.sh` report a violation of the named invariant.
- A planted wrong function in the real code must break the conformance test.
- Plant each one with `"$U/scripts/control.sh" --replace PATH 'OLD' 'NEW' -- <command>`. A control that stays green means that the proof or the test does not see that defect. Report it first.

## The receipt

Keep it beside the model, for example in `formal/RECEIPT.md`:

- the theorems or properties, each with the invariant that it proves and the invariant's author;
- the `lean-check.sh` output: only `propext`, `Classical.choice` and `Quot.sound`, and no `sorry`; or `tlc.sh` exited 0 with the deadlock check on;
- the conformance command and its result, and each control and its result;
- the drift note: the sha256 of each model file and the commit of the code that it mirrors (`shasum -a 256 formal/lean/**/*.lean`, `git rev-parse HEAD`). When the code changes after that commit, run the proof, the conformance test and the controls again.
