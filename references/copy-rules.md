# Copy rules

The text that understando and its agent write for the user says what happens, once, in the place where it applies. It does not reassure, and it does not comment on itself.

Two gates keep to this. Both run in code, so a prompt that breaks a rule does not render.

1. **Banned copy.** `scripts/prompt.py` (`banned_copy`, called by `check` and `render`) and `understando doctor` (the `copy-banned` finding, for the docs) read one list: [copy-rules.json](copy-rules.json).
2. **Strict STE.** Write every text that a reader sees by applying the **asd-ste100** skill. The skill is required and has no adapted copy. Then the text must pass `scripts/ste.py` (the lint of the skill) with 0 hard violations. The lint already refuses a semicolon, a sentence of more than 25 words, a synonym that rotates, a marketing word, a soft phrasal verb and a frozen action noun. This file does not repeat those rules.

## What the rules refuse

| Rule | What it finds | Instead |
|---|---|---|
| `nothing-claim` | A sentence that says what does not happen: "Nothing runs", "Nothing is approved", "Nothing is posted". | Say what the step writes, in the **Writes** field of the Next line. Say it once. |
| `until-you-say` | "... until you say", "... until you choose". | Delete it. Every prompt already waits for the pick. |
| `only-copies` | "It only copies." | Say what the control does. |
| `browser-only` | "Saved in this browser only." | Say where the data is, only where it changes a decision. |
| `tacked-on-no` | "no commit", "no push", "no force-push", "no rebase" or "no model call" in an option, a question or a situation line. | Put the fact in the **Writes** or **Cost** field of the Next line. |
| `tool-promise` | "understando never ...", "I never ...". | Say what the step does. |
| `stock-word` | "just", "simply", "easily", "basically", "actually", "of course", "don't worry", "please note" and the like. | Delete the word. |
| `run-in-label` | A label that opens a sentence: "In plain words.", "Why this matters:", "In short,", "Note:". | Write the sentence that the label introduces. |
| `comfort` | "no surprises", "you stay in control", "completely safe". | Delete it. |
| fragment slogan | A sentence of 1 to 4 words that ends in a full stop: "Done.", "Nothing runs.", "It stays open." | Join it to the sentence that it belongs to, or say what happens in 5 words or more. |
| repeated sentence | The same sentence in two places of one prompt (the situation, the question, the options). | Say it once, where it applies. |

A banned pattern in the list is a regular expression. To add one, add a row to `copy-rules.json`. The row has an `id` and the places it applies (`prompt`, `doc`). It has the `fields` (`all`, or `outside-next` to allow it in the Next line), the `pattern` and a `say` line. Then add the row to this table.

## The positive rule

- **A prompt option has a `label` and a `does`.** The `label` names the choice. The `does` says what happens when the user picks it, and nothing else.
- **The "Something else" option** has the label "Something else". Its `does`, when it needs one, is "Tell me what to do instead."
- **Facts that change the decision** (a commit, a push, a cost, a paid call, a file that is written) go in the Next line: **Scope**, **Cost**, **Time**, **Writes**. They go in the option text only when they apply to that option alone. Never in both places.
- **A situation line** reports a state. It does not comment on the state.
- **A report or a progress line** says what ran, what passed and what changed. It does not say that something is safe.

## Docs

The same list applies to `SKILL.md`, `commands/`, `references/` (also `references/adapted/`) and `cards/`. Doctor refuses a banned phrase in them. A doc that quotes a sentence for an agent to say (inside double quotation marks, ending in a full stop) must not quote a fragment slogan.

`references/copy-rules.md` and `references/adapted/unslop-core.md` are exempt, because they name the patterns that they refuse.
