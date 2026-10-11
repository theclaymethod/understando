# Tier 5: Lean model of a Python rule, plus conformance

Use for a **pure rule**: a function whose output depends only on its inputs (an accept rule, a score, a picker). The Lean model is a transcription of the Python. The theorems state the claim. Conformance proves that the model and the real function agree.

This is the method of the `lean-formal-feedback-loop` skill (written for Rust), adapted to Python. The adaptations are listed at the end.

## Project layout

```
<project>/formal/lean/
  lean-toolchain            leanprover/lean4:v4.34.1 (core only; no Mathlib, so it builds offline)
  lakefile.toml             lean_lib <Name>; lean_exe vectors (root Vectors)
  <Name>.lean               imports each model module
  <Name>/<Rule>.lean        the model and its theorems
  Vectors.lean              prints the conformance vectors; `--oracle` answers stdin
  Attempt/*.lean            proof attempts outside the default targets (may not build)
  <rule>_vectors.jsonl      committed vectors (one JSON object per line)
```

Run `lake build` in that directory. Add `.lake/` to `.gitignore`.

## Model

- Same guards, same order, same early returns as the Python. A Python `int` is `Int` (or `Nat` when the code makes it non-negative). A `Sequence` is a `List`. A `set` built from a comprehension is a `List` with a membership test, so the model stays decidable.
- Abstract only what the theorem does not read, and say so in a comment: "fields `quote`, `why` and `hint` do not reach the rule".
- A Python precondition that the code does not check (for example `states[-1]` on an empty list) becomes a hypothesis of the theorem. Report it as a precondition, not as a proof.
- Keep the functions computable (`def`, not `noncomputable`). The vectors executable and `decide` both need them.

## Theorems and proofs

- State the claim as written, then the claims it implies. Prove each one with `unfold`, `split`, `simp`, `omega`, `decide` or induction on the list.
- Try a **bounded** statement first (`∀ t < 6, ...` with `decide`) when the full proof is not obvious. A refuted `decide` prints "proved that the proposition ... is false": that is a concrete counterexample, so search for it with a `witness` function next.
- Check with `formal_lean.py check --project DIR --import <Name> --theorem <Ns.thm> ...`. Green needs `#print axioms` to list only `propext`, `Quot.sound` and `Classical.choice`, and no `sorry`, `admit` or `axiom` in the source.

## Conformance

1. `Vectors.lean` prints one JSON line per input: an edge grid (each boundary of each guard, ±1) plus pseudo-random inputs from a fixed LCG seed. Each line holds the inputs and the model's output. Run `formal_lean.py vectors --exe vectors --out <rule>_vectors.jsonl`; in CI use `--check` (the drift gate for the vectors).
2. With `--oracle`, the same executable reads one input per stdin line and prints the model's output. That is the live oracle for random inputs.
3. A Python property test (pytest or unittest, in the project's own test suite) loads the vectors, builds the real inputs, calls the real function and compares. A second test sends random inputs, about half of them near a guard's boundary, to the oracle when `FORMAL_ORACLE` is set. Without Lean installed, the vector test still runs, so the project CI needs no Lean.
4. Compare only **observable decisions**: return values, raised errors, the index that is picked. Never compare private state.

## Controls

- Model control: `formal_lean.py control --file <Name>/<Rule>.lean --symbol <theorem|def|lemma name> --match '<guard>' --op replace-with --with '<wrong guard>'` (an anchor edit; the edit of `formal_run.py --edit` has the same keys: op, path, symbol, match, with). The build must go red on a theorem.
- Code control: `formal_run.py --cwd <project> --copy <project> --link .venv --edit '<json edit>' --expect red -- <conformance test command>`. The conformance test must go red.
- When a control stays green, the theorem or the test cannot see that defect. Strengthen it before you rate anything.

## The 7-check conformance pass

| Check | Question for a Python rule |
|---|---|
| statement_parity | Do the theorem's hypotheses and conclusion match the function's preconditions, return values and errors? Are the non-goals written down? |
| state_parity | Does each Lean type match the Python value it stands for (int, None, list order, set semantics)? |
| transition_parity | Does each branch and early return of the function have a counterpart in the model? |
| concurrency_parity | Pure rule: `n/a`. Otherwise the rule belongs in tier 4. |
| cancel_drain_parity | `n/a` unless the rule handles cancellation or partial results. |
| runtime_evidence | Is the conformance test green on the vectors and on random oracle inputs? Is there a witness test for each open blocker? |
| drift_gate | Is the record stamped with the commit and blob of the mapped Python file and the hash of each model file? |

## Artifact record

`formal_record.py build --kind lean --tier 5` with the check JSON, the conformance run, both controls, the card and the 7-check file; then `stamp --code <py file> --model <lean files> <vectors>`. The record holds the theorem hashes (sha256 of each theorem's source block), the axioms, the ledger of controls and the drift stamp.

## Adaptations from lean-formal-feedback-loop

| Original (Rust, asupersync) | Here (Python) |
|---|---|
| `cass` session-history mining for `BugPrior` | `git log --oneline -S '<symbol>' -- <file>` and `git log -20 -- <file>` in the reviewed repo; a fix or revert on the same surface raises BugPrior |
| `cargo test --test refinement_conformance` | the project's own pytest or unittest command, from its reviewed CI profile |
| `ProofWitness` const in `src/formal/witnesses.rs` | the artifact record in the sidecar; the reviewed repo gets only the model, the vectors and the tests |
| proptest variants in `tests/lean_generated/` | the Python property test against the vectors and the `--oracle` executable |
| `evidence_ledger.jsonl` | the sidecar `runs/<repo>/<pr>/formal/verifiers.json`, one record per frog |
| staleness by `git log` timestamps | `formal_record.py drift`: blob of each code file and sha256 of each model file |
| lab seeds and interleaving traces as witnesses | a counterexample input from a Lean `witness` search, written into a regression test by `formal_witness.py test` |
| target tiers C + E | ladder tiers 4 + 5 for loops and rules; tier 2 when no cheap model exists |

Kept as is: one frog at a time; the EV ranking and the Bayes update (a concrete counterexample is BF 8, a blocker that is only tactic order is BF 0.2); proof friction is evidence; the four routes with the code-first bias; one change per iteration; split the theorem after two failed iterations; no claim without a witness, a conformance run and a hash.
