<!--
adapted-from: skills/principle-build-the-lever/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: principle-build-the-lever
-->
# Build the lever

When the work is not trivial, build the tool that does it or proves it instead of doing it by hand.

**Why.** Throughput: a codemod, generator or script does the work the same way every time and reruns for free. Confidence: the tool is one artifact a reviewer reads and reruns. Hand-done changes can only be re-verified by redoing them.

- Do the first unit by hand to learn the recipe, then build the tool. Prove it by rerunning it on that unit and diffing against your hand-done version. Make it safe to rerun.
- Use a codemod or script for edits, a generator for repetitive files, a query for analysis, a rerunnable check for verification.
- A deterministic lever beats fan-out. If one script can process every unit, run it yourself.
- When you fan out to subagents, write the lever as a file they all read (recipe, verification contract, do-not-touch fences), outside their write scope.
- Applying this principle produces a file. If the diff has no codemod, script, generator or delegate brief, you did not apply it.
- Commit the lever when the work outlives the session.

**Balance.** The bar is triviality, not repetition. A one-off earns a lever when the lever makes the work checkable. Build the smallest script that does or proves the job, never a framework.

Done when: a reviewer can rerun one command and get the same result.

**Where understando applies it.** controls and generators a reviewer reruns (a probe control or a generated test is a lever; commit the script, not a transcript of running it by hand).
