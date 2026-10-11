# doctor

Run `understando doctor`. Each finding has a severity that says what to do:

Each stop of this playbook ends with one question to the user. Ask it as [Asking the user](../references/working-rules.md#asking-the-user) tells you: the situation, a Next line, and numbered options.

- **auto:** no decision. Run `understando doctor --fix` once, and report what it moved in one line.
- **mention:** the user must know. Say each one in one sentence with its fix. A missing optional skill is a mention, never an error: understando then uses its adapted copy or its built-in rule.
- **route:** a verb closes it. Name the verb and the gap. Run the verb only when the user asks.

It looks for these problems:

- Schema drift, and stale stored verdicts.
- A promise, claim or check name that is not plain: a cut of `plain.what`, a path, a tool name or a code name. The fix is a name of 2 to 6 words that you write (`commands/map.md`).
- A trust map behind the PR head.
- A proof or a model older than its code.
- The explainer runtime, and the learn app (paused).
- Missing toolchains.
- A link in the skill docs that points at no file.
- Routed skills, and adapted copies older than the installed original.
- A deleted `@cc` contract comment in the PR or on the ready branch.
- Stale imported evidence.
- The skill links and the CLI link.
- The per-repo `understando.toml`: the key source, the key file, the budget, the protected paths and the owners of deferred invariants.
- An unapproved CI profile, a ready worktree behind origin, and stale lock entries.
- A committed vectors file under `formal/` with no committed generator. With `--formal`, doctor generates each `formal_tlc.py` vectors file again and compares it byte for byte.

An empty list is the good result. Say so in one line.
