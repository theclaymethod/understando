# doctor

Run `understando doctor`. Each finding has a severity that says what to do:

- **auto:** no decision. Run `understando doctor --fix` once, and report what it moved in one line.
- **mention:** the user must know. Say each one in one sentence with its fix. A missing optional skill is a mention, never an error: understando then uses its adapted copy or its built-in rule.
- **route:** a verb closes it. Name the verb and the gap. Run the verb only when the user asks.

It looks for these problems:

- Schema drift, and stale stored verdicts.
- A trust map behind the PR head.
- A proof or a model older than its code.
- The explainer runtime, and the learn app (paused).
- Missing toolchains.
- Routed skills, and adapted copies older than the installed original.
- A deleted `@cc` contract comment in the PR or on the ready branch.
- Stale imported evidence.
- The skill links and the CLI link.

An empty list is the good result. Say so in one line.
