<!--
adapted-from: skills/poteto-mode/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: poteto-mode
-->
# Subagents

A subagent is a separate agent run you start with a scoped brief: the Claude Code Agent tool, `codex exec`, or the equivalent in your host. A delegate is the same thing. Use whichever your host offers.

## Defaults for every subagent

- Run it in the background so you keep working. Wait only when your next action depends on its result.
- Pass file pointers, not inlined context. Name the files, the contract and the success criterion, and let the subagent read them.
- Set an explicit model per role (code, prose, judgment). Send the hardest changes to your strongest model. Send trivial mechanical edits to your fastest.
- Give each subagent one narrow scope and an explicit write fence.

## Ownership

You own every subagent's work. Review its diff, rerun its check yourself, and write your own summary. Do not pass through what it said.

After an interrupted chain, start a fresh subagent with the consolidated scope. Resumed chains silently drop directives, so a "done" summary from one is not evidence.

Done when: you have read the diff, rerun the check, and written your own summary.

## Second opinion

A second opinion is the same prompt run on a model from a different family, in a fresh context. Agreement between the two is a strong signal. Disagreement is a finding to investigate before you proceed. This is the model-verifier rule: a verifier is a different family from the author and starts with no shared context.
