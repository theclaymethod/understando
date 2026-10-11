<!--
adapted-from: skills/principle-sequence-verifiable-units/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: principle-sequence-verifiable-units
-->
# Sequence work into verifiable units

Order work as small units, each ending in a state you can check. Do not advance until the current unit is green.

**Why.** A break caught at the unit that caused it is cheap to localize. A break caught after a batch is buried, and you have already built on a broken base. Delivering the units in an order a reviewer can replay turns "trust me" into "watch it go red, then green".

**Execution.** In a sweep, a migration or any run of similar edits, verify each change before the next. Each unit is a bracket: known-good state, one change, run the check, then proceed. Rebase onto clean trunk first so each check measures against the real baseline. When a script does the edits, the per-unit check is nearly free. Run it anyway.

**Delivery.** Stack commits in the order that proves the work. The canonical shape is the failing test first, then the fix on top. Other orders are a subtraction before the reshape, a baseline capture before the treatment, the scaffold before the feature. Each commit lands on its own and the sequence reads as an argument.

Pairs with prove-it-works (keeps each check real) and build-the-lever (makes each check cheap).

Done when: each unit ended in a passing check before the next began.

**Where understando applies it.** `build` (one verified unit at a time, verifier red before code) and `close` (close one claim, check it, then the next).
