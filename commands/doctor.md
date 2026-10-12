# doctor

Run `understando doctor`. Each finding has a severity:

- **mention:** the user must know. Say each one in one sentence with its fix. A missing optional skill is a mention: understando then uses its adapted copy.
- **route:** a verb closes it. Name the verb. Run it only when the user asks.

It checks the toolchains (Lean, TLA+, the mutation venv, cc-check), the required asd-ste100 skill and the routed skills, the skill and CLI links, the links in the skill docs, the evidence store (its schema, its code refs and control anchors at the head, the drift of each formal record), and the shape of the verify skill. An empty list is the good result: say so in one line.
