# Understando

Understando helps you turn the spec in your head into behavior you can verify. Start with something an agent did. What did you expect? What did the evidence show? Your judgment updates a working spec, and a check preserves that decision for the next change.

Suppose you ask an agent to create a support ticket. It gives you a link as soon as the request enters the queue. A trace shows that no ticket was saved at reply time. You clarify that success means the ticket exists and the link opens that record. Understando revises the clause and links a delayed-save replay that distinguishes a premature reply from a valid one. How to report a failed save remains an open decision.

## Use it

- **Recover an intention.** “Here’s a recording and my review. Draft the behavior I expected. Which parts are still your inference?”
- **Refine a spec.** “Compare this ticket and run with the PStack decision log. Show which clause or check needs to change, and what evidence would settle the open question.”

Run this repository’s `install.sh` from the target project to install the Claude Code skill. It also removes the original Understando commit-hook registration on upgrade. For other agents, install [SKILL.md](SKILL.md) using their skill installer.
