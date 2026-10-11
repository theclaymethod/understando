# Tier 2: property and fuzz tests

Use when the input space is large and no cheap model exists, or as the conformance half of tier 5. For each claim, write a **property** (a predicate that must hold for every input) and a **generator** (the inputs). The control is a planted bug that the property must catch.

## Tool by language

| Language | Library | Run |
|---|---|---|
| Python | Hypothesis (`@given`, `st.*`) when the project already depends on it | the project's pytest command |
| Python, no Hypothesis | a seeded `random.Random(seed)` loop plus an exhaustive grid of small inputs | the same test command |
| TypeScript | fast-check (`fc.assert(fc.property(...))`) | the project's test command |
| Rust | proptest (`proptest! { ... }`) | `cargo test` |

Add a test dependency to the reviewed repo only with the user's approval. A seeded stdlib generator needs no new dependency and runs offline.

## Generators

- Put weight on the boundaries: each guard's threshold ±1, empty collections, one element, duplicates, ties.
- Generate structured values (findings, records) from small alphabets, so collisions (equal keys, equal scores) happen often.
- Fix the seed and print it on failure. Hypothesis shrinks a failing input; with a stdlib loop, also run an exhaustive grid over a small domain, so the smallest counterexample is found.

## Properties

- An algebraic law (order, idempotence, monotonicity) or a reference model (a Lean model through its vectors or `--oracle`, or a slow and obvious Python version).
- Compare observable decisions only.

## Control

Plant one bug in the real function in a scratch copy (`formal_run.py --cwd <project> --copy <project> --link .venv --edit '<json edit>' --expect red -- <test command>`). The property must go red. A green control means that the generator never reaches the bug: widen it.

## Record

`formal_record.py build --kind property --tier 2`. A tier 2 record is never Formal; it backs a claim, and it is the conformance evidence for a tier 5 record.
