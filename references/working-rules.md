# Working rules

understando works on its own. When an original skill is installed, understando routes to it. Otherwise it uses the adapted copy under `references/adapted/`, which is usable alone. Sources and licences are in `../THIRD_PARTY_NOTICES.md`, and `adapted/manifest.json` lists every copy.

When Poteto Mode is active, it owns reply style, subagent rules and autonomy. understando keeps only its exceptions. `discover`, claim wording and waivers stop for the user, even under full autonomy.

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
| code-contracts | `@cc` contracts at tier 3; else write the contract by hand, and `cc-check format` checks it |
| create-verification-skill | e2e drivers for a CLI, TUI or service; the user starts it |
| expect | e2e checks of a web UI; else tester-army `npx e2e` with `E2E_TELEMETRY_DISABLED=1` |
| lean-formal-feedback-loop | formalize at tier 5 |
| interrogate, nemesis-review | the independent review in `ready`; else `adapted/code-review.md` |
| show-me-your-work | the decision log; `understando note --export-tsv` writes the same columns |
| simplify, ultra-clean, deslop | trim gate 2; else the built-in pass: probe-proven deletion plus a dead-code tool |
| no-comments | comment cleanup; it keeps each `@cc` contract comment |
| technical-writing | docs and PR text; else the reply rules and the STE lint |
| asd-ste100, visual-explainer | required: the STE lint and the explainer runtime. setup installs them |
