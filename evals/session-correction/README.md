# Revising checks after a developer correction

The first turn establishes three download decisions, one undecided boundary and two direct observations. The second turn corrects the expected result for an active transfer. In one branch the developer leaves queued requests undecided; in the other they decide to deny them. The earlier r12 run remains the only direct evidence. No product or application check is executed by this interview.

The synthetic project uses an existing four-row check list. The runner captures the actual Markdown file at both turns of the same Codex thread. A pass requires the right situation, outcome and evidence status for every row at each turn. The two replies are supplied by the fixture regardless of what question the skill asks. This measures recording and revising the developer's decisions within a provided schema. It leaves the quality of an unscripted interview and discovery of new cases open.

Use the [shared C-Stack interview runner](https://github.com/theclaymethod/cstack/tree/293753c67ad4d225643aa7ce40b15bd09e77f5a2/evals/bootstrap/correction) from a checkout at that commit with an authenticated Codex CLI. From this repository:

```sh
runner=/path/to/cstack/evals/bootstrap/correction
python3 "$runner/controls.py" evals/session-correction/case.json
python3 "$runner/interview.py" --case evals/session-correction/case.json --skill SKILL.md --branch in-flight --out /tmp/understando-in-flight
```

Repeat with branch `queued` and a fresh output path. To compare another revision, supply its exported SKILL.md. The 26 controls exercise accepted row reordering, stale expectations, wrong evidence classifications, dropped decisions, changed situations and duplicate IDs. Frozen inputs and skill hashes are recorded alongside each pair of artifacts.

## Observed file changes

| Row | First turn | After the in-flight correction | After both decisions |
| --- | --- | --- | --- |
| A, returning reader makes a new request | deny, proposed | same | same |
| B, transfer already in progress | deny, observed pass | finish, observed conflict | finish, observed conflict |
| C, active link | finish, observed pass | same | same |
| D, queued before revocation | open | open | deny, proposed |

The revoke-button check earns no credit for blocking a download. The old transfer observation remains evidence of what r12 actually did even though it conflicts with the corrected promise.

Both branches passed for the original skill (fe3b1fb), the previously published skill (4a23fe1), the first candidate and the final candidate. Each result is one trial per branch. The extra candidate revision addressed a separate playback evidence failure and the complete correction interview was rerun. [Final in-flight result](results/candidate/in-flight/result.json) · [Final queued result](results/candidate/queued/result.json)
