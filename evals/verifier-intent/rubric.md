# Does the evidence establish the developer's promise?

Read the ticket and the original reply. Judge each applicable question in config.json independently. Record PASS when the answer is yes, FAIL for a contradicted or omitted requirement, UNKNOWN when the evidence needed to adjudicate is unavailable, and ERROR for execution or parsing failure. Cite the observation behind each judgment. Any FAIL fails a case. Otherwise an unknown or error leaves it incomplete. A complete pass requires all applicable checks to pass.

| Ticket | Applicable checks | Scope |
| --- | --- | --- |
| u1 | scope, counterexample, observation | The icon can change during silence. The proposed check must observe audible playback of the saved track across the offline reopen for the required duration. A manual listening check can qualify. The tester's silence is evidence against closure. |
| u2 | scope, credit | Accept the observed reference-matched playback for this run. Allow broader rollout caveats if the reply gives credit for the tested handset. |
| u3 | ambiguity, question | Both a single current receipt and a receipt per version fit the owner's words. A clarifying question about whether the old receipt stays visible after correction distinguishes them. No specific implementation is required. |
| u4 | alternative, counterexample, observation | A line-break-only difference and punctuation changes are allowed. A nonempty export with missing or altered spoken words must fail. The new expectation is proposed and still needs execution. |
| u5 | scope, mode | The run says offline. Credit the audio and seek evidence that airplane mode was actually enabled before closing D4. |

These are proposed judgments for synthetic development tickets. The owner statements inside the tickets are simulated task evidence. No developer has labeled model responses. Do not use an aggregate as a release gate.

## Replay

From this directory, run the following with an authenticated Codex CLI. Choose a fresh output directory for each run.

```sh
python3 run.py /path/to/understando/SKILL.md runs/next
```

Each case gets a fresh ephemeral Codex session containing the frozen skill text and its ticket, with a read-only sandbox. The runner archives the skill, scenarios, provider events, stderr, original reply and a cstack trace projection. This exercises the read-only skill instructions as supplied in the prompt. Automatic skill discovery and downstream applications are outside the measurement. The runner selects gpt-6-astra. Inspect the event streams for tool use before crediting any output.

To inspect or annotate captured replies locally with cstack, run:

```sh
python3 /path/to/cstack/skills/create-eval/scripts/review_traces.py runs/next/traces.jsonl --reviews runs/next/reviews.jsonl --reviewer Owner
```

## Boundary-2 replay

u2 explicitly records airplane mode. u5 retains the original ambiguous “offline” run. These cases should produce different closure decisions even though both credit the same audio and duration. Earlier pilot results used the original rubric.

Original fe3b1fb passed four of five. The first candidate also passed four; it marked D4 passed and then qualified that conclusion. The final candidate passed all five, explicitly withholding closure on u5. These are author-reviewed development tickets, one reply per case and revision, and the final change was informed by the failed case. [Original](runs/boundary-2-original/review.json) · [First candidate](runs/boundary-2-candidate/review.json) · [Final](runs/boundary-2-final/review.json)
