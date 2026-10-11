<!--
adapted-from: skills/principle-subtract-before-you-add/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: principle-subtract-before-you-add
-->
# Subtract before you add

When evolving a system, remove complexity first, then build.

**Why.** Adding to a complex system compounds complexity. Removing first leaves less code, reveals the essential structure, and usually makes the next design obvious. Default to subtraction. Leave the design slightly simpler and more capable behind the same or a smaller surface than you found it.

- Sequence removal before construction.
- Cut before you polish. Reach the minimum before investing in quality.
- Design for observed usage, not speculative edge cases.
- Add no validators, parsers or guards beyond what the spec demands.
- Simplify prompts: remove redundant instructions and excessive templates.
- Delete a reference with no novel content instead of leaving a stub.

Done when: the removals are made and the checks still pass before any addition starts.

**Where understando applies it.** `trim` (delete unit tests and excess code before anything is added).
