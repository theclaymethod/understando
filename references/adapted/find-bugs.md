<!--
adapted-from: skills/find-bugs/SKILL.md
source: agent-guards
source-version: c86d619
license: MIT, Copyright (c) 2025 Matthew Lam. See THIRD_PARTY_NOTICES.md.
original-skill: find-bugs
-->
# The finding format

Each bug that understando reports uses one format. discover uses it for an answer that the code does not obey. formalize uses it for a code-first route, and close and the review use it for their findings. `scripts/findings.py` writes it.

```text
P1 — [Small fix, 95% finding confidence, 90% fix confidence] <one line>
  Trigger: <the input or the edge case>
  Expected: <what the contract says>. Actual: <what the code does>.
  Impact: <what goes wrong for a user or the system>
  Fix: <the fix direction that the two estimates are about>
  Evidence: <the run, the test or the witness that shows it> (ref: ...)
```

- **The heading.** The priority (P0 to P3), the size of the fix (Small, Medium, Large), the finding confidence and the fix confidence. Put the numbers in the heading, so that the reader can scan them.
- **No invented numbers.** A rating that nobody gave shows as "not rated".
- **Bugs and leads apart.** A finding is a bug only when the execution path and the contract both support it. That is a confirmed invariant and a run that gives the other result. Else it is a lead. List the leads under their own heading.
- **Understand first.** Trace the entry points, the callers, the tests, the state changes and the failure paths before you judge the code.
- **Prove the important ones.** Show a consequential finding with a focused run: a witness test, a reproduction or a control.
- **Not bugs.** A style preference, an intentional trade-off and an edge case that cannot occur are not correctness bugs.
- **Read only.** Report the bug. Do not fix the code unless the user asks. A code-first bug from formalize goes to the author with its witness test.
