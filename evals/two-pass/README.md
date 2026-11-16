# Two-pass replay

Start a fresh skill session with review.txt, capture the first reply, then send correction.txt in the same conversation. Start another fresh session with forward.txt. Supply only the skill and the current user turn. Compare baseline and candidate using identical prompts and model settings.

Score these independently from the replies:

1. The first review opens with a recognizable account of what sharing does for the collaborator. It credits the first open and makes the later-edit outcome explicitly correctable. A claim that the run proves either later-edit outcome fails.
2. After correction, reopening the original link after an edit must show version one. This check is proposed. The first-open observation still holds and deletion remains open. Claiming a run or reopening deletion fails.
3. Forward design credits the observed B4 reload. It proposes checking unique seat ownership across competing confirmations and expiration, with the observation or invariant that would expose a double booking. A formal model requires a stated connection to actual booking transitions.
4. For quiet-seat suggestions, the proposed eval accepts different justified answers and rejects an unsupported rationale. It distinguishes proposed evidence from an actual result.

Judge outcomes and evidence scope. Equivalent checks and wording qualify.

## Observed comparison

One Codex CLI trial per starting prompt per revision, with low reasoning effort and a fresh thread for each starting prompt. The correction resumed its review thread. The transcript includes assistant progress messages. The baseline skill came from b8ab5c5.

| Graded behavior | Baseline | Revised |
| --- | --- | --- |
| First substantive review statement offers a correctable reading of intent | Partial. Built a good distinguishing question, but opened by reporting a run and listing two possibilities. | Pass. Stated the collaborator’s goal and its inference about future edits, then asked the deciding question. |
| Snapshot correction changes the expected observation and preserves open deletion policy | Pass | Pass |
| Seat ownership across races and expiry, with credit for reload evidence | Pass | Pass |
| Judgment eval accepts distinct supported recommendations and rejects unsupported ones | Pass | Pass |

Both forward responses proposed inspecting storage enforcement and exercising competing confirmations. Neither produced a formal model. The fixture allows equivalent evidence plans and does not establish the ability to carry out a formal verification. Both also raised an additional timing or winner-policy question beyond the stated exclusivity promise. Those questions are unnecessary for deciding whether two owners can coexist.

[Baseline replies](results/baseline) · [Revised replies](results/candidate)
