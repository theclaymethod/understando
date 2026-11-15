# Understando

Ask Understando **“Where should I spend my review time on this change?”** It follows the user’s intended outcome through the code and the available evidence, then points to the assumption worth double-checking. If the evidence already answers the question, it shows you where.

For example, a change updates both an invitation email and its confirmation badge. The badge looks right. The delivery check counts one queued job. A reviewer’s time is better spent on the retry path: **after the first delivery succeeds but its acknowledgement is lost, how many invitations reach the recipient?** Understando finds the deciding procedure, checks what PStack has already verified, and identifies the observation that would settle the question.

## Use it

- **Review a change.** “Review this diff against the ticket. Show me the most consequential assumption our checks could miss.”
- **Sync a spec.** “Use this owner decision to update the spec and its eval index. Which existing checks now have the wrong expectation?”

Run this repository’s `install.sh` from the target project to install the Claude Code skill. It also removes the original Understando commit-hook registration on upgrade. For other agents, install [SKILL.md](SKILL.md) using their skill installer.
