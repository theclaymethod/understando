<!--
adapted-from: skills/principle-model-the-domain/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: principle-model-the-domain
-->
# Model the domain

Encode the real domain in a data structure instead of scattering it across conditionals.

**Why.** Scattered booleans, repeated shape assumptions and branching spread across files are accidental complexity. A structure that matches the domain makes invalid states unrepresentable and deletes branches. Choosing it at write time is cheap. Recovering it later reads as a refactor and gets deferred.

**Reach for structures like these.**

- A state machine instead of scattered booleans, phases or lifecycle checks.
- A typed object or model instead of loose parameters.
- A map, registry, lookup table or discriminated union instead of branching spread across files.
- A reducer or command and event model instead of ad hoc mutation.
- A module organized around one body of domain knowledge, not a sequence such as load, validate, transform, save. Execution order is not ownership.
- A queue, cache, index, graph or normalized collection where the access pattern calls for it.
- When none fits, work out what the code must never allow and how the data gets read, then find the structure that encodes exactly that.

Do not force an abstraction. Prefer boring code when the current shape is clear, local and unlikely to grow. Distrust an abstraction that adds indirection without removing branches, duplicated rules, invalid states or lifecycle risk.

**Signs you skipped this.** A feature grows an if/else chain by one branch. A second boolean must stay in sync with the first. Phase-named modules repeat the same domain rules.

Done when: the data shape is named and its structure is chosen before any logic is written.

**Where understando applies it.** tier 3 contracts and invariants (a contract names the data shape and the structure that makes illegal states unrepresentable).
