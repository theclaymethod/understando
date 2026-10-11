<!--
adapted-from: skills/principle-guard-the-context-window/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: principle-guard-the-context-window
-->
# Guard the context window

The context window is finite and non-renewable within a session. Spend each token on something that earns it.

**Why.** Overflow degrades reasoning, creates compression artifacts and halts progress.

- **Isolate large payloads.** Route verbose output, screenshots and large documents to a subagent. The main context gets a summary, not raw data.
- **Keep frequently used content inline.** Templates and references used on every run belong in the main file, not behind a read.
- **Size phases and cap scope.** Limit files per phase, set turn budgets, and count the cost of each mechanism.

Done when: the main thread holds summaries and pointers, and no raw payload larger than the decision it informs.

**Where understando applies it.** subagents (route bulk reading and verbose output to a subagent and keep only its summary).
