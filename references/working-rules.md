# Working rules

understando works on its own. When you install an original skill, understando routes to it. Otherwise it uses the adapted copy under `references/adapted/`, which is usable alone. Sources and licences are in `../THIRD_PARTY_NOTICES.md`, and `adapted/manifest.json` lists every copy.

When Poteto Mode is active, it owns reply style, subagent rules and autonomy. understando keeps only its exceptions. `discover`, claim wording and waivers stop for the user, even under full autonomy.

## Asking the user

Each stop of each playbook ends with one decision. Ask it as one question with numbered options.

1. Start with the situation, in 5 lines or fewer:
   - What moved: the PR head, and the commits on the ready branch after the last map.
   - Where the PR stands: the verdict counts, the merge verdict and the number of blockers.
   - What changed that affects the next step.
2. Then write one "Next:" line. It tells what the step does, its scope (the claim or check IDs), its cost ($ and model calls), its time and what it writes.
3. Then ask one question with 2 to 4 numbered options:
   - Option 1 is the recommended default, and it shows "(recommended)".
   - The last option is "Something else".
   - Each option tells what happens when the user picks it.
4. Stop. Wait for the pick. A pick in this conversation is the user's yes for that one option only.

The CLI writes the words. `understando review --json`, `menu --json`, `ci --question --json` and `close --next --json` give a `prompt` object: `{situation: [lines], next: {step, does, scope, cost, time, writes}, question, options: [{id, label, does, run, recommended}]}`. Relay it in this text format:

```text
<situation line 1>
<situation line 2>
Next: <does>. Scope: <scope>. Cost: <cost>. Time: <time>. Writes: <writes>.

<question>
  1. <label> (recommended): <does>
  2. <label>: <does>
  3. Something else: <does>
```

The text output of each of these commands is this render. Give it to the user as it is.

- Do not restate the CLI output. Summarise a long step output in 3 lines or fewer, then ask the next question.
- Do not show the verb table. Show it only when the user asks for it ("help", "all verbs", `menu --all`).
- Ask about one claim at a time, never all claims in one question.
- When the harness has a tool for a structured question, you can use it with the same options. The numbered text is the default: it works in each harness (Claude Code, Codex, Cursor).
- When the user picks an option, run its `run` command. When `run` names an answer file, write that file with the pick.

## Routes

| Rule area | Adapted file | Original skill | Used by |
|---|---|---|---|
| reply-rules | `adapted/reply-rules.md` | poteto-mode | explain, ready, close |
| subagents | `adapted/subagents.md` | poteto-mode | probe, ready, build, close |
| principle-prove-it-works | `adapted/principles/prove-it-works.md` | principle-prove-it-works | probe, trim, ready |
| principle-test-behavior-not-implementation | `adapted/principles/test-behavior-not-implementation.md` | principle-test-behavior-not-implementation | probe, trim, close, build |
| principle-sequence-verifiable-units | `adapted/principles/sequence-verifiable-units.md` | principle-sequence-verifiable-units | build, close |
| principle-subtract-before-you-add | `adapted/principles/subtract-before-you-add.md` | principle-subtract-before-you-add | trim, build, ready |
| principle-laziness-protocol | `adapted/principles/laziness-protocol.md` | principle-laziness-protocol | trim, ready |
| principle-model-the-domain | `adapted/principles/model-the-domain.md` | principle-model-the-domain | discover, formalize, build |
| principle-type-system-discipline | `adapted/principles/type-system-discipline.md` | principle-type-system-discipline | formalize, build, discover |
| principle-fix-root-causes | `adapted/principles/fix-root-causes.md` | principle-fix-root-causes | formalize, close |
| principle-attack-the-premise | `adapted/principles/attack-the-premise.md` | principle-attack-the-premise | formalize, close |
| principle-encode-lessons-in-structure | `adapted/principles/encode-lessons-in-structure.md` | principle-encode-lessons-in-structure | doctor, ready |
| principle-build-the-lever | `adapted/principles/build-the-lever.md` | principle-build-the-lever | probe, build, formalize |
| principle-guard-the-context-window | `adapted/principles/guard-the-context-window.md` | principle-guard-the-context-window | probe, ready, build |
| principle-never-block-on-the-human | `adapted/principles/never-block-on-the-human.md` | principle-never-block-on-the-human | discover, close, build, ready |
| feature-playbook | `adapted/feature-playbook.md` | poteto-mode | build |
| pr-verification | `adapted/pr-verification.md` | poteto-mode | ready |
| unslop-core | `adapted/unslop-core.md` | unslop | explain, ready |
| grilling | `adapted/grilling.md` | grilling | discover |
| writing-for-agents | `adapted/writing-for-agents.md` | writing-for-agents | explain, doctor, build |
| tdd-red-first | `adapted/tdd-red-first.md` | tdd | build, close |
| to-spec | `adapted/to-spec.md` | to-spec | formalize, explain |
| glossary-format | `adapted/glossary-format.md` | domain-modeling | discover, explain, formalize |
| code-review | `adapted/code-review.md` | code-review | ready |
| handoff | `adapted/handoff.md` | handoff | build, close |

## Routes with no adapted copy

When the original is missing, the step uses the built-in rule that `understando routes` prints.

| Skill | Used for |
|---|---|
| code-contracts | `@cc` contracts at tier 3. Else write the contract by hand, and `cc-check format` checks it |
| create-verification-skill | e2e drivers for a CLI, TUI or service. The user starts it |
| expect | e2e checks of a web UI. Else tester-army `npx e2e` with `E2E_TELEMETRY_DISABLED=1` |
| lean-formal-feedback-loop | formalize at tier 5 |
| interrogate, nemesis-review | the independent review in `ready`. Else `adapted/code-review.md` |
| show-me-your-work | the decision log. `understando note --export-tsv` writes the same columns |
| simplify, ultra-clean, deslop | trim gate 2. Else the built-in pass: probe-proven deletion plus a dead-code tool |
| no-comments | comment cleanup. It keeps each `@cc` contract comment |
| technical-writing | docs and PR text. Else the reply rules and the STE lint |
| asd-ste100, visual-explainer | required. They are the STE lint and the explainer runtime, and setup installs them |
