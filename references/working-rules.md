# Working rules

understando works on its own. When an original skill is installed, understando routes to it. Otherwise it uses the adapted copy under `adapted/`, which is usable alone. The sources and the licences are in `../THIRD_PARTY_NOTICES.md`, and `adapted/manifest.json` lists every copy.

## Writing

- **Claim and invariant text.** Write it by **applying the asd-ste100 skill** (`~/.agents/skills/asd-ste100/SKILL.md`). Follow its rules while you write. discover and `build claim` run its lint (`scripts/ste.py`) on the text and refuse a hard violation. The skill is required, with no adapted copy.
- **Prose for the user.** Lead with the outcome. Say what happens, once, in the place where it applies: no reassurance, no slogan. Name a check by what it checks; IDs, SHAs and paths go in a trailing `(ref: ...)` part. When a list has more than three items, name the top three and give the count. The rules come from concisely ([adapted/concisely.md](adapted/concisely.md)) and the reply rules ([adapted/reply-rules.md](adapted/reply-rules.md)).
- **Text for an agent** (a verify skill, a brief): follow [adapted/writing-for-agents.md](adapted/writing-for-agents.md): context pointers, steps with completion criteria, leading words, no no-ops.

## Asking the user

Each stop ends with one decision. Ask it as one question with numbered options: the situation in at most five lines, a Next line (scope, cost, time, what it writes), then two to four options. Option 1 is the recommended default; the last option is "Something else". Wait for the pick. A pick is the user's yes for that one option only.

A verb that runs commands prints them and stops without `--yes`. Relay the commands in the question, then run the same verb with `--yes` only after the user picks it.

## Subagents

Use subagents for independent read-only work: the source wave of maintain, one subagent for each feature file. Give each one a brief with its scope, what it must not do and the shape of its answer ([adapted/subagents.md](adapted/subagents.md)). A subagent never drives the app and never edits a file unless its brief says so.

## Findings

Each bug uses the format of [adapted/find-bugs.md](adapted/find-bugs.md): `P1 — [Small fix, 95% finding confidence, 90% fix confidence] <one line>`, then the trigger, expected and actual, the fix and the evidence. Keep verified bugs apart from leads.

## Routes

| Step | Original skill | Adapted copy |
|---|---|---|
| create | create-verification-skill (the user starts it) | [adapted/create-verification-skill.md](adapted/create-verification-skill.md) |
| maintain | maintain-verification-skill (the user starts it) | [adapted/maintain-verification-skill.md](adapted/maintain-verification-skill.md) |
| discover | grilling | [adapted/grilling.md](adapted/grilling.md) |
| build | tdd | [adapted/tdd-red-first.md](adapted/tdd-red-first.md), [adapted/feature-playbook.md](adapted/feature-playbook.md) |
| formalize, rung 5 | lean-formal-feedback-loop | [lean-python.md](lean-python.md) |
| a `@cc` contract | code-contracts (`cc-check format`) | none: write the contract by hand, then run `cc-check format` |
| claim text | asd-ste100 (required) | none |
| export | visual-explainer renders the data | none |
| principles | the pstack principle skills | [adapted/principles/](adapted/principles/) |
