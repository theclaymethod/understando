# Evidence bars

This file is the only source of the evidence bars. Other docs link here, and they do not restate a bar. `scripts/onto.py` (`surfaces`, `bar`, `BARS`) is their only implementation. When the two disagree, the script is the fact and this file has a bug.

Different kinds of work need different evidence. A claim names one surface, and the surface sets the bar that the claim must meet.

## Surfaces and their bars

Each claim has a surface, and each surface has a bar. A claim meets its bar when each of its parts meets it. `onto.bar` applies the rules.

| Surface | Detected from | Bar | Control |
|---|---|---|---|
| frontend | A TSX, JSX, CSS or HTML file, or a UI route. | An e2e run in a real browser against the real app, with a recorded video (`artifact.video`). A unit or component test is below the bar. | Break the UI. The e2e must fail. |
| backend | Other code. | Risky: a proof (Formal). Not risky: a property test, types, a contract or a static rule. An example test is below the bar. | As above. |
| llm | A prompt, a model call, a judge, a cartridge, a generator or a scoring rubric, or an eval or a model judgment as the check. | An eval: pre-registered, with a frozen judge or labels, blind when possible, with k ≥ 3 runs or a stated sample size, and recorded. | A planted-degraded variant (`eval.degraded`) must score worse. An eval with no degraded variant cannot show that it can fail. |
| other | No code and no llm check. | A check backs it. | As above. |

The user can set `surface` and `risk` on a claim. When a claim touches two surfaces, `map` prints a `surface:` line, and the agent asks the user once. `understando.toml` `[bars]` can change the bar of each surface and risk.

The merge verdict uses the bars. A risky claim below its bar blocks. A claim below its bar that is not risky is a risk to accept. The ladder tier stays visible as detail.

## Risk and the per-repo tuning

A claim is risky when it touches safety, cost, the anti-gaming rules of the editor, clinical output or production (`onto.risk_tags`). The user can also set `risk: true`. A merged claim is risky when one of its old claims was risky. `understando.toml` can change the bar of each surface and risk level:

```toml
[bars.backend]
risky = "formal"     # formal | static | property | test
normal = "property"
[bars.frontend]
risky = "video"      # video | e2e
[bars.llm]
normal = "eval"      # degraded-eval | eval
```

## Bars, parts and strength

- A claim meets its bar only when each of its parts meets it. The card names the first part below the bar.
- The bar does not change the strength of a claim. The strength still comes from the parts and their checks (verdicts.md). The page shows the bar next to the strength, and the ladder tier as detail.
- A check that meets the bar must also be able to fail. For a browser e2e or a backend check, a control caught its planted break. For an eval, a degraded variant scored worse.

## Where the bars show

- The explainer, the story: it names the bars that the PR met.
- The explainer, the merge verdict: it lists each risky claim below its bar.
- The explainer, the cards: each claim has a bar chip, and each promise shows "N of M claims meet their bar".
- The explainer, "Can these checks catch a bug?": it has one part for each kind of control.
- The PR section: a Surface and a Bar column, and one summary line.
- The review: the situation lines and the progress lines use the bar words.
- The ready checklist: gate 1 needs each risky claim at its bar, and each other claim at its bar or waived.
- `close` offers the way to the bar first.
