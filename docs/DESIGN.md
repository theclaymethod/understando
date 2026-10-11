# understando: design spec, agreed with Clayton on 2026-10-10 (explainer ladder revised the same day)

## Purpose

understando helps a reviewer decide what to trust in a large PR without reading every line.
- **Source:** Cindy Sridharan, "How to effectively debug when you no longer understand the code" (Oct 2026).
- **Thesis:** "Designing verification > understanding code."
- **Who:** the author's agent runs it, and the reviewer reads the result.

## Output (per PR)

1. **PR-body section.** It is short: a diagram, the headline claims-and-verdicts table, and short bullets. No long samples.
2. **Explainer.** Editable source plus HTML, built with the visual-explainer runtime and its default components. It is teaching material for a newcomer, also one outside the team: it gets a developer up to speed on the PR, then shows how strong the verification is. It is a level ladder: each level is one screen deep, and detail waits in collapsed blocks. One self-contained MDX unit per level:
   - **The story:** the problem, the change and why to trust it; one before-and-after diagram; one chip per promise with its weakest verdict; the glossary, collapsed.
   - **The loop:** the run steps, one plain sentence each, each tagged with its promise.
   - **What changed:** a before-and-after diagram and a "replaced by" table, both from the diff.
   - **The promises:** three to six plain promises, weakest first, each with its strength, a reviewer action when it is weak, and its claims collapsed; under each claim, collapsed, the code, the verifiers and the control results.
   - **Verify the verifiers:** red, green and cannot-fail; the controls animation; the verifier map with every layer.
   - **Changed code that no claim covers,** from the diff and the claim code refs.
   - **Trade-offs and concerns,** and the verifications of the explainer. **Exercises** is a placeholder for the learning app.
   - Levels 1 to 3 show no ID and no code name, except in the Detailed mode of a two-mode architecture diagram, in a table, or in a collapsed block. Each architecture diagram has a Simple (ELI5) and a Detailed mode.
3. **`trust-map.json`:** claims, verifiers, controls and verdicts, so a later run can diff against an earlier one.
4. **Storage:** everything lives under `~/dev/understando/runs/<repo>/<pr>/`, outside the repo under review.

**Style.**
- Prose is STE-flavoured.
- Claims, verdicts and verifier descriptions are strict STE (ASD-STE100).
- Run `python3 -I ~/.claude/skills/asd-ste100/scripts/ste-lint.py` to 0 hard violations.

## Model

**Claim ledger.**
- Each claim is one thing the PR asserts.
- A claim uses its Code Contracts `@cc` ID when one exists (https://code-contracts.cc). The `@cc` contracts are the requirements.

**Two tiers.**
- **Fact tier:** what tools observed: test runs, type-checker output, goldens, boundary checks, fuzz results, recorded evals, e2e transcripts and replays against the real app, and `cc-check format`.
- **Guess tier:** model judgements, PR narrative, repros, and `$code-contracts verify`.

**Verifier inventory.** All kinds are first-class:
- e2e tests;
- integration tests;
- type-system pins;
- golden and parity tests;
- static boundary checks;
- property tests and fuzzing;
- Lean proofs (optional);
- evals and measurements;
- model verifiers.

**Fields per verifier:**
- the claim or claims it backs;
- its tier, fact or guess;
- its control recipe and control result;
- its independence: tool, or model, and if model then which family and which context;
- its cost;
- its provenance.

**Verdict per claim:**

| Verdict | Meaning |
|---|---|
| Proven | A fact-tier verifier exists, and it went red on a planted bug (a control) |
| Backed | A verifier exists, but it was never control-tested, or it is model-judged |
| Asserted | Only the PR narrative says so |
| Gap | No verifier exists, and the claim is not stated. The reviewer decides. |

**Controls** (verifying the verifiers).
- Run cheap, model-free controls in a scratch worktree. Never touch the user's checkout.
- At least one control per verifier, from this catalogue:
  - remove a guard line;
  - invert a condition;
  - delete a type-contract pin;
  - drop an allowlist row;
  - corrupt one golden byte;
  - delete the code a test claims to cover.
- Record each recipe and its expected red.
- Flag loudly a verifier whose obvious control stays green: it checks nothing.
- Record expensive evidence (evals, paid e2e) with its provenance, but do not rerun it.

**Model verifiers.**
- Use a different model family from the author's. For example, use Codex/gpt to check Claude-written code.
- Give it a fresh context, with no PR narrative.
- A model verifier never rises above Backed unless it passes a control: it must flag a planted violation.
- This follows the post: the same model with the same context is "one opinion counted twice".

**E2E drivers,** chosen by surface:
- **CLI, TUI or service:** `/pstack:create-verification-skill` (at `~/.claude/skills/pstack/skills/create-verification-skill`).
  - The user must invoke it (`disable-model-invocation`), so understando prints the exact command.
  - That skill writes to `.cursor/skills/verify-<app>/`.
- **Web or mobile UI:** tester-army `e2e` (https://github.com/tester-army/e2e). Always set `E2E_TELEMETRY_DISABLED=1`.
  - A replay counts as a fact only when it ran against the real app.
- **Neither fits:** the claim is a Gap.

**Lean.**
- Flag candidates: small, pure, high-stakes invariants.
- Write a proof only when the user asks.
- A proof is a fact only when its spec-to-code link is checked, for example by an e2e test that runs the same cases through both.

**Writes into the reviewed repo.** New `@cc` contracts, e2e tests that close a Gap, and controls worth keeping go on a separate branch, as a patch, for the author. They never go into the PR's own commits.

**Budget.**
- The default is $0: record existing evidence, and run only model-free controls.
- Any paid step (model verifier, tester-army agent steps, eval replay) shows a cost projection and waits for the user's yes.
- Live OpenAI calls use only the key in `/Users/clayton/dev/function-intelligence/.env` for that repo. Never the keychain, and never a personal login.

## Packaging

**Location.**
- Repo: `~/dev/understando`, the git remote `theclaymethod/understando` (private).
- The old quiz skill is preserved as tag `quiz-v1`.
- Replace its files with a normal commit. Never force-push.

**Router skill `understando`** with five sub-commands, each a separate file the router points to:

| Sub-command | Job |
|---|---|
| `setup` | Global installs plus doctor |
| `map` | Build the claim ledger and the verifier inventory |
| `controls` | Run the model-free controls in a scratch worktree |
| `explain` | Build the three-level explainer and the PR-body section |
| `rerun` | Diff against the previous `trust-map.json` |

**Invocation.** The model may invoke `map` and `explain`. `controls` and per-repo setup run only on explicit user request.

**`setup.sh`.** It is idempotent and ends with `doctor`, which prints what is present and what is missing. It:
- symlinks the skill into `~/.agents/skills/understando`, `~/.claude/skills/understando`, `~/.codex/skills/understando` and `~/.cursor/skills/understando`;
- installs the Code Contracts skill: `npx skills add https://github.com/spolu/code-contracts`;
- makes `cc-check` (`@spolu/cc-check`) available;
- checks pstack create-verification-skill and maintain-verification-skill, the asd-ste100 skill, and the visual-explainer runtime (Artifacture, at `~/.artifacture` or the visual-explainer skill's repo), and installs any that are missing.

**Per-repo setup** runs on first use and only after user approval: `npx e2e init` (tester-army), and the Code Contracts line in `AGENTS.md`.

**Tests: end-to-end only, never unit tests.**
- **Fixture repo** (under `tests/fixture/`). It holds:
  - a good verifier, which must be rated Proven;
  - a verifier that cannot fail, which must be flagged and not rated Proven;
  - a claim with no verifier, which must be a Gap;
  - a narrative-only claim, which must be Asserted;
  - a model verifier, which must be Backed.

  The e2e runs understando `map` plus `controls` on the fixture, and asserts the verdicts exactly.
- **Second e2e target:** PR #489 in Function-Health/function-intelligence, read-only and model-free.

**visual-explainer.** Reuse its runtime and its cards (`explain-diff`, `code-walkthrough`, `web-diagram`). Add one new `trust-map` card inside understando. Do not fork visual-explainer.

**Skill writing.** Follow `~/.claude/plugins/cache/mattpocock/mattpocock-skills/1.3.1/skills/productivity/writing-for-agents/SKILL.md`:
- context pointers;
- steps with completion criteria;
- progressive disclosure;
- leading words;
- no no-ops.

Keep the router's description short.
