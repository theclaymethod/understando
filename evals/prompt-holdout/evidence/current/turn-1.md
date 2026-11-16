# Checks for offering `new_task`

Build 31 verifies one of three required prompt outcomes. The unattended and omitted-flag cases still need captures of what the model receives. The recorded runs do not support signing off on all three modes.

Use an ordinary interactive session as the baseline. For the two proposed checks, keep the model and other settings fixed, vary only the flag, and inspect the offered tools in the final outbound prompt. This verification method follows the developer’s stated contract and Runner B’s example. Registry membership is an implementation choice. [Developer decisions and Runner B](session.txt#L1-L5)

| Starting condition | Action | Required observation | Build 31 coverage |
| --- | --- | --- | --- |
| Interactive session, unattended flag explicitly false | Assemble and capture the prompt sent to the model. | The offered tools include `new_task`. | **Verified.** [Runner B](session.txt#L5) captured the final outbound generic-model prompt under this condition and observed the tool. |
| Unattended session, flag true | Assemble and capture the prompt sent to the model. | The offered tools exclude `new_task`. | **Proposed.** [Runner A](session.txt#L4) observed the availability predicate return false. [Runner C](session.txt#L6) observed no preview dialog during one task. Both could pass if the prompt still offered the tool and the task never used it. |
| Interactive session loaded from older settings with the flag absent | Assemble and capture the prompt using those settings. | The offered tools include `new_task`, as they do for explicit false. | **Proposed.** [Runner A](session.txt#L4) observed the predicate return true for both omitted and false. [Runner B](session.txt#L5) captured only explicit false, so a prompt assembly error specific to a missing flag would go undetected. |

**Open decision.** Whether to block a direct call to `new_task` outside the prompt remains undecided. Either direct-call outcome is compatible with these prompt checks. [Developer clarification](session.txt#L3)
