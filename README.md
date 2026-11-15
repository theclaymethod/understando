# Understando

Understando hunts for the implicit spec in your head. You can often tell that an agent did the wrong thing before you can say which rule it broke. Give Understando a recording, a diff, or a ticket. It writes down what it thinks you meant, checks that reading against the PStack decision log, and brings you the question whose answer would change the expected behavior.

Take “one click should send one invitation.” In a review scenario, the queue check passed after one enqueue. The recipient got two messages. You rule out duplicates and say a suppressed address may receive nothing. The clause becomes **“One click may deliver at most one invitation.”** Whether an eligible recipient must always get one is still open. [Walk through the example](https://claytonkim.com/understando#example)

Understando updates the affected clause, or drafts it if there’s no spec yet. The queue check stays linked to what it measured. For the delivery rule, Understando proposes an E2E check that follows one click into the recipient’s inbox and counts the messages. An existing eval or checked statechart property can serve the same purpose if it covers that promise.

## Use it

- **Recover an intention.** “Here’s a recording and my review. Draft the behavior I expected. Which parts are still your inference?”
- **Refine a spec.** “Compare this ticket and run with the PStack decision log. Show which clause or check needs to change, and what evidence would settle the open question.”

Run this repository’s `install.sh` from the target project to install the Claude Code skill. It also removes the original Understando commit-hook registration on upgrade. For other agents, install [SKILL.md](SKILL.md) using their skill installer.
