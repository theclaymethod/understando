<!--
adapted-from: skills/principle-encode-lessons-in-structure/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: principle-encode-lessons-in-structure
-->
# Encode lessons in structure

Encode recurring fixes in mechanisms (tools, code, metadata, automation) instead of textual instructions. Every error, human correction and unexpected outcome is a learning signal. Capture it, route it, close the loop.

**Why.** Text is easy to miss. It needs the reader to notice, remember and comply. A lint rule, metadata flag, runtime check or script enforces the rule without cooperation.

When you catch yourself writing the same instruction a second time:

1. Ask whether it can be a lint rule, a metadata flag, a runtime check or a script.
2. If yes, encode it and delete the instruction.
3. If no (it needs judgment), make the instruction more prominent and add an example of the failure.

**Pick the strongest mechanism.** In order: an unrepresentable state that cannot compile, a lint or banned API that fails CI, a canonical helper, a runtime check. Agents copy what the surrounding code does, so a weaker guard becomes the next template. If the fix is structural, use only the structural fix.

**Feedback loop.** Capture every correction and decide whether it is a one-off or a pattern. Route it: a one-off goes to a note, a recurring fix to a skill or lint rule, a systemic issue to a principle. Apply it now or create a concrete todo.

**Anti-patterns.** Acknowledging without recording. Recording without routing. Fixing one instance while leaving the pattern intact.

Done when: the lesson exists as a mechanism that fails on a repeat, and the instruction it replaces is deleted.

**Where understando applies it.** `doctor` (a recurring problem becomes a check that `understando doctor` runs, not another line of instruction).
