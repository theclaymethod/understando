# Understando

Use Understando when a ticket changes what someone should experience. It recovers the intended behavior from project decisions and user evidence, reconciles it with the spec, and links each rule to the checks that exercise it. PStack runs the project's verification.

For example, ask: “Use Understando on this ticket. Does marking a film unwatched still reset playback when an older save arrives? Show me the decision, the procedure, and the assertion that covers it.”

## Install

Run this repository's `install.sh` from the root of the target project to install the Claude Code skill. For other agents, install the root [SKILL.md](SKILL.md) using the agent's skill installer.

If upgrading from the pre-commit quiz, remove the Understando command ending in `.claude/hooks/understando-gate.sh` from the target project's Claude Code hook settings. Preserve other hook entries. Existing installations can have a registration even after the skill file has been replaced.

## Use

Ask for a review to see the intended outcome, evidence, and gaps. Ask for a sync to update the project's spec and verification index. A ticket can start with a user correction or a recording even when it has no spec document. The skill distinguishes supported intent from assumptions that need a decision.
