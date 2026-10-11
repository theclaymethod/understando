<!--
adapted-from: skills/principle-fix-root-causes/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: principle-fix-root-causes
-->
# Fix root causes

When debugging, trace every problem to its root cause and fix it there. Do not fix symptoms.

**Why.** Symptom fixes accumulate. Each workaround makes the system harder to reason about and the real bug remains. Root-cause fixes are slower up front and reduce total debugging time.

- Reproduce first.
- Ask why until you reach the root cause.
- Add no guard. A nil check that silences a crash is a symptom fix.
- If a workaround needs a paragraph of comment to justify it, fix the code, not the comment.
- Check for the pattern, not just the instance. Search for the same pattern and fix every instance.
- When stuck, instrument. Add logging and read the actual error instead of guessing.

**Restart bugs.** When something fails after a restart, suspect stale persistent state first: config files, caches, lock files, serialized state. If clearing a state file restores behavior, make state validation the fix.

Done when: the failure reproduces before the fix, passes after it, and the same pattern is searched for elsewhere.

**Where understando applies it.** code-first routes from `formalize` (a code defect found while formalizing is fixed at its cause, not guarded).
