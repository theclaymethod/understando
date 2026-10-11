<!--
adapted-from: skills/principle-laziness-protocol/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: principle-laziness-protocol
-->
# Laziness protocol

Aim for the most result with the least code and complexity.

- **Prefer deletion.** When asked to refactor or improve, look for removals before additions.
- **Keep the call hierarchy flat.** If answering a question means tracing more than 3 files or layers, flatten it. A rich interface that hides substantial work is not a deep call chain.
- **Consolidate decisions.** Put each choice behind one source of truth and pass the result as a simple flag.
- **Minimize the diff.** Make the smallest change that solves the problem. Fewer lines beat elegant boilerplate.
- **Question the threading.** If a task asks you to pass a new signal through types, schemas or pipelines, look for a more direct path first.
- **Sweat the small leaks.** Remove pass-throughs, representation leaks and duplicated choices before they spread.

**The test.** If a human developer would find the code exhausting to maintain, it is a bad solution.

Done when: every addition in the diff has a reason that no deletion or smaller change could meet.

**Where understando applies it.** `trim` (the smallest diff, deletion over addition, excess code flagged).
