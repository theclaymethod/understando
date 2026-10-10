# rerun

Diff a new trust map against the previous one, after the PR gets new commits.

## Steps

1. **Keep the old map.** Copy `$M` to `$R/trust-map.<old head SHA>.json`.
   - **Done when** the copy exists.
2. **Update the map.** Set `head` to the new SHA. Run `map` steps 3 to 6 for the changed files only. Keep each claim ID, so the diff can match claims.
   - **Done when** `validate.py` prints `VALID`.
3. **Run the controls again**, when the user asks for it. Follow [controls.md](controls.md). Without new control results, the old results stay in the map, and the diff shows no change for them.
   - **Done when** each control has a result at the new head, or the user declined.
4. **Diff.** Run `python3 $U/scripts/verdicts.py $M`, then `python3 $U/scripts/rerun.py $R/trust-map.<old head SHA>.json $M --fail-on-drop`.
   - **Done when** the diff prints. Report each line that starts with `DROP` word for word.
5. **Explain again.** Follow [explain.md](explain.md) when a verdict changed.
   - **Done when** the explainer shows the new head SHA, or no verdict changed.
