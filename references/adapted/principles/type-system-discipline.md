<!--
adapted-from: skills/principle-type-system-discipline/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: principle-type-system-discipline
-->
# Type system discipline

The type checker is a proof assistant. Use it to eliminate impossible states, mismatched primitives and unhandled variants at compile time. Define errors and special cases out of existence instead of proliferating handlers. Applies to any typed language.

- **Make illegal states unrepresentable.** Model variants as sum types (discriminated unions, enums with payloads, sealed classes). Do not model state as a bag of optional fields where contradictory combinations compile. `{ completed: boolean; completedAt?: Date }` admits `completed: true` with no date. Derive the boolean from `completedAt !== null`, or write `{ kind: 'open' } | { kind: 'done'; at: Date }`.
- **Build types from the values you want.** A non-empty list is a head plus a rest. A valid time range is a start plus a duration. Choose the shape that cannot build the illegal value.
- **Brand semantic primitives.** `UserId` and `OrderId` are strings underneath and must not be interchangeable. Validate once at creation, trust the type downstream.
- **Parse external data at every boundary.** RPC payloads, JSON, CLI args, config, environment variables and database rows are untyped until a parse function turns them into the model.
- **Do not lie to the type system.** A cast or an assertion that bypasses the compiler is a latent crash. Prove the fact (validate, narrow, refine the model) or treat the cast as a hazard.
- **Match exhaustively.** The compiler must fail when a new variant goes unhandled.
- **Derive from authoritative schemas.** When a schema, spec or migration defines a shape, derive the type from it.
- **Strengthen a type only where partiality appears.** A runtime assertion or "should never happen" throw marks a type that is too weak. Push the check into the type, then stop. Prefer total functions.

**Tests.** Can you write a comment explaining when a field combination is valid? Split it into a sum type. Do two arguments share a primitive but mean different things? Brand them. Where did this `any` or `as` come from? Validate at the boundary. Will the compiler tell the next agent where a new variant needs a case?

Done when: each partiality marker (cast, throw, comment about valid combinations) is gone or justified.

**Where understando applies it.** tier 3 contracts and invariants (state the invariant as a type or a total function where the language can hold it).
