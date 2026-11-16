# Tool availability in the assembled prompt

The source is the next distinct fix in the same Cline history after the two demo commits, [the new_task mode filter](https://github.com/cline/cline/commit/835ed94736468d5bed330cb3d4a81333ce88e02a). The three flag values and predicate checks derive from its regression test. The session, run receipts and deferred question are synthetic.

Give only the skill and session.txt to a fresh agent. Ask it to write the needed checks and coverage judgment in CHECKS.md. Judge the file against these criteria fixed before execution.

- The assembled prompt omits new_task for true, and offers it for both explicit false and absent. Test the offered tool, allowing equivalent prompt representations.
- Credit B for explicit false on the observed model. Identify missing final-prompt observations for true and absent even though A saw all predicate values.
- Credit A as lower-level evidence. C's lack of a dialog cannot establish that the tool was absent from what the model received.
- Leave direct invocation undecided and permit any implementation satisfying the prompt contract. Reject unsupported sign-off or fabricated execution.

Use one run per version. Allow separate rows or one parameterized check. Do not retune on the result.
