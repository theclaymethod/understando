<!--
adapted-from: skills/engineering/tdd/SKILL.md
source: mattpocock-skills
source-version: 1.3.1
license: MIT, Copyright (c) 2026 Matt Pocock. See THIRD_PARTY_NOTICES.md.
original-skill: tdd
-->
# Red-first loop

Test-driven development is a red then green loop. Apply every section on every cycle.

Read `GLOSSARY.md` if it exists so test names match the project's domain language.

## What a good test is

A test verifies behavior through a public interface, not implementation details. Code can change entirely and the test should not. It reads like a specification ("user can checkout with valid cart") and survives refactors.

## Seams

A seam is the public boundary you test at. Tests live at seams, never against internals. Before writing any test, write down the seams under test and confirm them with the user. Write no test at an unconfirmed seam. Ask "What is the public interface, and which seams should we test?"

## Anti-patterns

- **Implementation-coupled.** Mocks internal collaborators, tests private methods, or verifies through a side channel. The tell is a test that breaks on a refactor with no behavior change.
- **Tautological.** The assertion recomputes the expected value the way the code does (`expect(add(a, b)).toBe(a + b)`). Take the expected value from an independent source: a literal, a worked example, the spec.
- **Horizontal slicing.** Writing all tests first, then all code. Bulk tests verify imagined behavior. Work in vertical slices instead: one test, one implementation, repeat. Each test is a tracer bullet that responds to what the last cycle taught you.

## Rules of the loop

1. **Red before green.** Write the failing test first. Prove it fails for the right reason. Then write only enough code to pass it. Add no speculative features.
2. **One slice at a time.** One seam, one test, one minimal implementation per cycle.
3. **Refactor outside the loop.** Refactoring belongs to the review stage, not the red then green cycle.

Done when: each slice has a test seen red for the stated reason, then green with minimal code.
