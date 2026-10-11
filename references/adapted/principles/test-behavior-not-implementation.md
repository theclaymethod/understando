<!--
adapted-from: skills/principle-test-behavior-not-implementation/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: principle-test-behavior-not-implementation
-->
# Test behavior, not implementation

A test calls the code the way its users do and asserts the result they observe against a literal expected value. A test that asserts which calls the code made, or restates a constant the code contains, does neither.

**The check.** Before you keep a test, ask whether it would still pass if every function it imports returned `undefined`. If yes, it observes no behavior and cannot fail for a defect. Rewrite the assertion or delete the test.

**Why.** A test that cannot fail for a defect costs CI time and review attention and catches nothing. A constant pin also fails when someone edits the constant, so it prevents that edit.

**Five shapes that still pass when every import returns `undefined`.**

- Weak or no assertion. No `expect`, or only `toBeDefined`, `toBeTruthy`, `not.toThrow`, `toBeInstanceOf`, `toBeGreaterThan(0)`.
- Mock or absence only. Only `toHaveBeenCalled`, `not.toHaveBeenCalled`, `toBeUndefined`, `toEqual([])`, `toHaveLength(0)`.
- Self-referential. The expected value comes from the code under test: `expect(f(a)).toBe(f(a))`.
- Constant pin. The assertion restates a hand-maintained constant, default, table row or prompt string.
- Fixture asserts fixture. The assertion reads data the test built, and the subject never runs in the body.

**The fix.** Call the subject inside the test body with one concrete input and assert the literal output or the observable effect, as in `expect(slugify("Hello, World!")).toBe("hello-world")`. For an absence, assert the presence on the other input in the same test. For a constant, test the mechanism that reads it with one input. For a mock, assert the payload it received or the state after the call. When no such assertion exists, delete the test.

**Keep** a test of a relation across a table's rows (a key present in two tables, a parent that exists) and a compile-time check.

Done when: every kept test calls the subject and asserts a literal or an observable effect.

**Where understando applies it.** `probe` (a control must observe behavior) and `trim` (a unit test that fails this check is a deletion candidate).
