# Understando

Do your verifiers actually capture what you intend? Understando helps you answer that question when designing checks and when reviewing them.

**Forward pass.** Start with a feature idea or spec. Understando uses Bootstrap's interview technique to find the cases where reasonable interpretations differ. It changes one detail at a time and asks what should happen. After each topic, you confirm or correct its readback. The confirmed behavior tells you what each verifier should observe.

**Backward pass.** Start with the assertions in your existing tests and evals. Understando explains the user experience they imply and asks whether that matches what you meant. If you correct its reading, it identifies which results still hold and which verifier needs work.

For example, opening a new share link and seeing the current document proves that the link works on first open. A snapshot and a live link both pass. Edit the document and open the original URL again. Which version should the reader see? Your answer determines the assertion. [Explore both passes](https://claytonkim.com/understando)

**Thread review.** Understando reads a conversation and asks you to confirm what you wanted. It then traces the first decision that took the work away from that intent. If a skill could prevent a repeat, you choose the edit and Understando tests it against the original decision.

## Use it

For a new feature, try "I want readers to share documents by link. Interview me about what sharing should do before we write the checks."

For a diff, try "Read the verifiers for this change. Tell me what you think I intended and where you had to infer it. Let me check your reading."

For a retrospective, try "Read this thread back to me. Once we agree on what I meant, find where the work drifted and help me change the skill that would have caught it."

To install the Claude Code skill, run this repository's [install.sh](install.sh) from your target project. On upgrade, the installer removes the old Understando commit hook. For other agents, use their skill installer with [SKILL.md](SKILL.md).

## Checking interview changes

With CStack checked out beside this repository, run `BOOTSTRAP_SKILL=../cstack/skills/bootstrap/SKILL.md bash tests/check.sh` to check that both skills ship the same interview instructions.
