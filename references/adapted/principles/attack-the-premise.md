<!--
adapted-from: skills/principle-attack-the-premise/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: principle-attack-the-premise
-->
# Attack the premise

When two or more fixes that share one premise have failed the same gate, suspect the premise, not the fixes. Each failure under a shared premise is evidence about the premise.

1. **Write the premise down.** It is the one sentence every failed fix assumed.
2. **Take a census before the next fix.** Count the imbalance per actor, as a rerunnable script. The census shows which actors hold the imbalance, not how large it is.
3. **Read the skew.** If the same few actors hold most of the imbalance on every run, something assigns them that role. Find what assigns it. That is the next "why" under fix-root-causes.
4. **Remove the asymmetry instead of compensating for it.** Rotate the role, randomize the assignment, or move the role, so no actor holds it on every run. A return path, a shared pool or a periodic rebalance leaves the assignment in place and adds work on every run.

**Stop.** Do not start the next fix before the premise is written down and the census exists. If the census is even across actors, the premise is not the cause. Look elsewhere and keep the census as evidence.

Done when: the premise sentence and the census output exist before the next fix begins.

**Where understando applies it.** code-first routes from `formalize` (repeated failed fixes under one claim mean the claim or design is the suspect).
