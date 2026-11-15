# Understando

Understando hunts for the implicit spec in your head and helps you encode it in checks your project can run. Start with something an agent did. Which outcome would you accept? Which would make you ask for a fix? Your judgment supplies the expected result for an eval, an end-to-end test, or a checked statechart property. The check itself can carry that part of the spec.

Take “one click should send one invitation.” In the review scenario, the queue check passed after one enqueue, but the recipient got two messages. You reject the duplicate and say a suppressed address may receive nothing. The proposed inbox test waits for processing and retries to settle, counts the messages delivered by that click, and asserts `deliveries <= 1`. Replaying the duplicate would fail. A suppressed address receiving nothing would pass. Whether an eligible recipient must always get one is still your call. [Walk through the example](https://claytonkim.com/understando#example)

Use PStack’s verification toolkit or the project’s existing runner to create or update the check. Link it to the example or decision that explains the expectation. If a written spec already describes that behavior, keep it in sync. A project with no spec document can start directly with the test. When your intention changes, revisit the expected result and rerun it.

## Use it

- **Recover an intention.** “Here’s a recording and my review. Find the expectation behind my correction. What other outcome would you need me to judge before turning it into an eval?”
- **Codify a decision.** “Compare this run with the PStack decision log. Find or build the check that would catch the behavior I rejected and still pass for the case I accepted.”

Run this repository’s `install.sh` from the target project to install the Claude Code skill. It also removes the original Understando commit-hook registration on upgrade. For other agents, install [SKILL.md](SKILL.md) using their skill installer.
