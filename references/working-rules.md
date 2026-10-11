# Working rules

understando works on its own. When you install an original skill, understando routes to it. Otherwise it uses the adapted copy under `references/adapted/`, which is usable alone. Sources and licences are in `../THIRD_PARTY_NOTICES.md`, and `adapted/manifest.json` lists every copy.

When Poteto Mode is active, it owns reply style, subagent rules and autonomy. understando keeps only its exceptions. `discover`, claim wording and waivers stop for the user, even under full autonomy.

## Asking the user

Each stop of each playbook ends with one decision. Ask it as one question with numbered options.

1. Start with the situation, in 5 lines or fewer, in plain words:
   - What moved: new PR commits that the review branch does not have, and fixes on the review branch that are not checked yet.
   - Where the PR stands: the verdict counts in words ("5 proven formally, 22 proven by tests") and the merge verdict with its blocker count. The count is the count of the explainer's merge verdict.
   - What changed that affects the next step. Examples: the explainer (open, or out of date), the CI approval, a lock, and code excerpts that point at moved code.
2. Then the Next line: one short sentence. Under it, one line with the scope, the cost ($ and model calls), the time and what the step writes.
3. Then ask one question with 2 to 4 numbered options:
   - Option 1 is the recommended default, and it shows "(recommended)".
   - The last option is "Something else".
   - Each option tells what happens when the user picks it.
4. Stop. Wait for the pick. A pick in this conversation is the user's yes for that one option only.

The order of the first questions is fixed. First bring in the new PR commits (a merge). Then ask for the CI approval, then link each new test on the review branch, then run the re-check. Each one is its own question.

The CLI writes the words. `understando review --json`, `menu --json`, `ci --question --json`, `close --next --json` and `open --json` give a `prompt` object: `{situation: [lines], next: {step, does, scope, cost, time, writes}, question, options: [{id, label, does, run, recommended}], details: [lines]}`. Relay it in this text format:

```text
<situation line 1>
<situation line 2>
Next: <does>.
Scope: <scope>. Cost: <cost>. Time: <time>. Writes: <writes>.

<question>
  1. <label> (recommended): <does>
  2. <label>: <does>
  3. Something else: <does>
```

The text output of each of these commands is this render. Give it to the user as it is. `details` holds the IDs, SHAs and paths, and `--verbose` shows them.

- Do not restate the CLI output. Summarise a long step output in 3 lines or fewer, then ask the next question.
- Do not show the verb table. Show it only when the user asks for it ("help", "all verbs", `help --all`).
- Ask about one claim at a time, never all claims in one question.
- When the harness has a tool for a structured question, you can use it with the same options. The numbered text is the default: it works in each harness (Claude Code, Codex, Cursor).
- When the user picks an option, run its `run` command. When `run` names an answer file, write that file with the pick.

## Reporting

These rules come from concisely ([adapted/concisely.md](adapted/concisely.md)). They apply to each prompt, each stop report and each final report.

- **Lead with the outcome.** Say first what changed, what passed, or what the state is now.
- **Plain names in prose.** Name a claim by its `name` or its promise. Name a check by what it checks, and a commit by what it did. IDs, SHAs, paths and line numbers go only in a trailing `(ref: ...)` part, in `--verbose` output, or in JSON fields. `scripts/prompt.py` refuses a prompt that shows a bare ID, a SHA or a `path:line`.
- **Prioritise.** When a list has more than three items, name the top three and give the count.
- **Call out decisions, blockers and residual risk.**
- **After each stop**, say what was checked, what passed and what changed for the reviewer. For example: "The idle stop is now proven: its new test catches the planted bug." Then ask one question. Link to the part of the explainer, for example "I opened its promise". Do not open a new page on each step.
- **While a stop runs**, print one plain line for each finished item, with ✓ or ✗ and one plain reason. `--json` gives the same lines as NDJSON events with an `id`.

## Findings

Each bug that understando reports uses the finding format of [adapted/find-bugs.md](adapted/find-bugs.md): `P1 — [Small fix, 95% finding confidence, 90% fix confidence] <one line>`, then the trigger, expected and actual, the impact, the fix and the evidence. Keep verified bugs apart from leads.

## After a miss

When the user finds a bug that the review missed, find the owning cause before you add a rule (from learn-from-mistake):

- **Verification:** the wrong surface was checked, or the check cannot fail. Add a check and a control that goes red on the same class of bug, and show it with probe.
- **Repository:** a structure or a missing deterministic check made the bug easy. Report it to the owner.
- **Task boundary:** context, access or tools were missing. Fix the boundary.
- **Judgement:** the setup was adequate. Fix the result, and add no machinery.

Do not add prose when a check can enforce the rule. Do not say that the prevention works before a control shows it.

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
| teach | `adapted/teach.md` | teach | review, open |
| concisely | `adapted/concisely.md` | concisely | every verb |
| find-bugs | `adapted/find-bugs.md` | find-bugs | discover, formalize, close, review |
| explain-report | `adapted/explain-report.md` | explain-report | explain (the content rules only) |
| autoreview | `adapted/autoreview.md` | autoreview | ready, when interrogate and nemesis-review are missing |

## Routes with no adapted copy

When the original is missing, the step uses the built-in rule that `understando routes` prints.

| Skill | Used for |
|---|---|
| code-contracts | `@cc` contracts at tier 3. Else write the contract by hand, and `cc-check format` checks it |
| create-verification-skill, maintain-verification-skill | e2e drivers for a CLI, TUI or service, and their upkeep. The user starts it. Their proof standards are the tier-1 rules in `controls.md` |
| expect | e2e checks of a web UI. Else tester-army `npx e2e` with `E2E_TELEMETRY_DISABLED=1` |
| lean-formal-feedback-loop | formalize at tier 5 |
| interrogate, nemesis-review | the independent review in `ready`. Else `adapted/autoreview.md` |
| show-me-your-work | the decision log. `understando note --export-tsv` writes the same columns |
| simplify, ultra-clean, deslop | trim gate 2. Else the built-in pass: probe-proven deletion plus a dead-code tool |
| no-comments | comment cleanup. It keeps each `@cc` contract comment |
| technical-writing | docs and PR text. Else the reply rules and the STE lint |
| asd-ste100, visual-explainer | required. They are the STE lint and the explainer runtime, and setup installs them |
