# Understando

At code review, Understando reads the verifications and tells you in its own words what it thinks you wanted the end user to experience. Correct that reading and it traces your correction through the checks and their earlier results. Starting from a spec, it works forward to the evidence that would distinguish the intended outcome from a plausible mistake.

In the invitation example, the queue check counted one request, but the recipient got two messages. You rule out duplicates and confirm that a suppressed address can receive nothing. The proposed test waits for retries to finish, counts the deliveries caused by one click, and asserts `deliveries <= 1`. It catches the duplicate. Whether an eligible address must receive a message is a separate decision. [Try the invitation example](https://claytonkim.com/understando#example)

Use PStack's verification toolkit or your project's test runner to create or update the check. Link it to the decision that explains the expected result. If that decision changes, update the check and any existing written spec.

With CStack installed, Understando can use Bootstrap to pick the question that separates two plausible rules, then use Adversarial Cases to challenge the proposed check. For example, an immediate open of a shared link shows the same image whether the link snapshots the cover or follows later changes. Replace the cover before opening the same link and the two rules predict different images. Ask which the developer intended before turning either prediction into a scored row.

## Use it

For a recording, try "I rejected the second invitation. What test would catch it and still allow a suppressed address to receive nothing?"

For a diff, try "Compare this change with the PStack decision log. Which user outcome could go wrong while our current tests still pass?"

To install the Claude Code skill, run this repository's [install.sh](install.sh) from your target project. On upgrade, the installer removes the old Understando commit hook. For other agents, use their skill installer with [SKILL.md](SKILL.md).
