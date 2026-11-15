# Understando

Understando looks for the implicit spec behind your corrections to an agent's work. Show it an outcome you rejected and one you would accept. The difference tells you what to check in a test, an eval, or a statechart. That check can be the first place you record the rule.

In the invitation example, the queue check counted one request, but the recipient got two messages. You rule out duplicates and confirm that a suppressed address can receive nothing. The proposed test waits for retries to finish, counts the deliveries caused by one click, and asserts `deliveries <= 1`. It catches the duplicate. Whether an eligible address must receive a message is a separate decision. [Try the invitation example](https://claytonkim.com/understando#example)

Use PStack's verification toolkit or your project's test runner to create or update the check. Link it to the decision that explains the expected result. If that decision changes, update the check and any existing written spec.

## Use it

For a recording, try "I rejected the second invitation. What test would catch it and still allow a suppressed address to receive nothing?"

For a diff, try "Compare this change with the PStack decision log. Which user outcome could go wrong while our current tests still pass?"

To install the Claude Code skill, run this repository's [install.sh](install.sh) from your target project. On upgrade, the installer removes the old Understando commit hook. For other agents, use their skill installer with [SKILL.md](SKILL.md).
