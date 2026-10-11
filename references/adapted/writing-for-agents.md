<!--
adapted-from: skills/productivity/writing-for-agents/SKILL.md and skills/productivity/writing-for-agents/SKILL-MECHANICS.md
source: mattpocock-skills
source-version: 1.3.1
license: MIT, Copyright (c) 2026 Matt Pocock. See THIRD_PARTY_NOTICES.md.
original-skill: writing-for-agents
-->
# Writing for agents

Use when you write any document an agent reads: a skill, an `AGENTS.md` or `CLAUDE.md`, a doc reached by a pointer. The agent takes the same process each run, so write the levers that make the process predictable.

## Context pointers

A context pointer is a reference held in the agent's context that names out-of-context material and the condition for reaching it. A skill description is one. A line in `AGENTS.md` naming a doc is another. The pointer's wording, not its target, decides when and how reliably the agent reaches the material. Sharpen a weak pointer before inlining its target.

- State what the material is and list the branches that should trigger reaching it.
- Front-load the leading word.
- Give one trigger per branch. Collapse synonyms that rename one branch.
- Cut identity the body already carries.

## Two loads

Always-loaded text costs context load on every turn. Documents the human must remember cost cognitive load. Material behind a pointer pays only the pointer's line.

## Information hierarchy

A document holds steps (ordered actions) and reference (facts and rules consulted on demand). Rank material by how immediately the agent needs it.

1. In-file steps. What the agent does, in order.
2. In-file reference. Consulted on demand.
3. Disclosed reference. A separate file behind a pointer, loaded when the pointer fires.

Inline what every branch needs. Push behind a pointer what only some branches reach. Keep a concept's definition, rules and caveats under one heading. A document too long, even with unique lines, thins attention. Split by branch or sequence.

## Steps and completion criteria

End every step on a completion criterion that tells the agent the work is done.

- Clarity. The agent can tell done from not done. A vague bound ("understanding reached") invites premature completion. Sharpen the bound first.
- Demand. How much the criterion requires. "Every modified model accounted for" forces more legwork than "produce a change list".

The strongest criteria are checkable and exhaustive.

## Leading words

A leading word is a compact concept the model already knows (lesson, tracer bullet, red). Repeat it as a token, never as a sentence. Reach for an existing word before coining one. "A loop you believe in" becomes red: the loop goes red on the bug or it does not.

State the target behavior positively. A prohibition drags the banned behavior into context. Use one only as a hard guardrail you cannot phrase positively, and pair it with the positive target.

## Pruning

- One source of truth per meaning. Duplication costs tokens and inflates prominence.
- The environment (scripts, config, directory layout, `--help`) is a source of truth. Restate it only when the lookup is expensive. Cache what the agent cannot find by looking: unwritten conventions, reasons, gotchas.
- Check each line for relevance. Stale layers settle because adding feels safe and removing feels risky.
- Hunt no-ops sentence by sentence. An instruction the model already obeys by default pays load to say nothing. Delete the whole sentence.

## When the document is a skill

- A model-invoked skill keeps a `description` carrying the trigger branches so the agent can fire it and other skills can reach it. It costs permanent context load.
- A user-invoked skill sets `disable-model-invocation: true`. Its description is a one-line human summary. Zero context load, but the human must remember it.
- Choose model-invocation only when the agent or another skill must reach it on its own.
- A router skill is one user-invoked skill that names the others and when to reach for each. It can only hint.

Done when: every step ends in a checkable criterion, each pointer names its triggers, and a no-op sentence scan finds nothing.
