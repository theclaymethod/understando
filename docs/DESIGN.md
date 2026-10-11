# understando: design spec, agreed with Clayton on 2026-10-10 (explainer ladder revised the same day)

## Purpose

Each claim has an evidence bar for its surface (frontend, backend, llm or other). The bars, their controls and their effect on the merge verdict are in [evidence-bars.md](../references/evidence-bars.md). Do not restate a bar here.

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
4. **Storage:** run state lives under `~/.understando/runs/<repo>/<pr>/`: local, outside the repo under review, and never in a git repo. `UNDERSTANDO_RUNS`, `runs_root` in `~/.understando/config.toml` or `runs_dir` in the per-repo config moves it. Every verb refuses to write a run folder inside a git repo, and doctor flags run output that any repo tracks. understando's own repo keeps only the test fixture (`tests/fixture`). A review is shared on purpose only: `understando publish` (commands/publish.md).

**Style.**
- Every text that a reader sees (claims, plain text, names, promises, the explainer narrative, prompts, reports, the PR section, journal summaries) is strict STE (ASD-STE100). The agent writes it by applying the asd-ste100 skill, which is required and has no adapted copy.
- The CLI gates the text with `scripts/ste.py`, the lint of that skill, to 0 hard violations: the prompt render, `map`, `validate.py`, `discover answer`, `close` wording, the PR section and the README of `publish`.
- The text says what happens, once, in the place where it applies. `references/copy-rules.md` lists the banned copy, and `scripts/prompt.py` and `doctor` refuse it.

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

**The mode `understando`** (`/understando` in Claude Code, `$understando` in Codex). `SKILL.md` is a short router: a bare invocation turns the mode on (`understando mode on`), runs `understando menu` (two or three verbs from `signals`, with reasons, then the verb table), and never runs a verb by itself. `commands.json` is the one source for the verb table, `--help` and the menu; `scripts/gen_router.py` writes the table into `SKILL.md`.

**One CLI.** `bin/understando <verb>`, linked into `~/.local/bin` by setup, runs every verb from any agent's shell. Each verb takes `--repo`, `--pr`, `--run` and `--json`. The skill text names no tool of one agent, so Claude Code, Codex, Cursor and any agent that reads `~/.agents/skills` work the same way.

| Verb | Category | Who starts it |
|---|---|---|
| `map` | Understand | the agent or the user (it always diffs against the previous map; it replaces `rerun`) |
| `discover` | Understand | the user (invariants with the user, before any verifier) |
| `probe` | Understand | the user (the controls; it replaces `controls`) |
| `formalize` | Understand | the user (tiers 4 and 5; a router stub) |
| `import` | Understand | the agent or the user (outside evidence, with a format check) |
| `close`, `trim` | Get ready | the user |
| `explain` | Share | the agent or the user |
| `learn` | Share | the user (paused) |
| `ready` | Run all | the user; `ready --report` also the agent |
| `build` | Run all | the user |
| `setup`, `doctor` | Maintain | setup the user; doctor the agent or the user |

**The verification ladder,** per claim as `tier`: 1 e2e or integration; 2 property or fuzz; 3 types, `@cc` contracts and static rules; 4 model checking (TLA+); 5 a Lean proof with conformance. A rung counts only after a control shows that its check can fail. Rungs 4 and 5 also need a passing conformance link to the real code. The verdict **Formal** sits above Proven for such a claim.

**Intent.** A claim reaches Proven or Formal only when the PR states it, or when it links to an invariant that the user confirmed in `discover`. An invariant that the agent picks alone is `author: agent` and caps its claim at Backed.

**The intent ledger.** `~/.understando/runs/<repo>/<pr>/journal.jsonl`, append-only and local only, with the columns of the show-me-your-work decision log (what, why, evidence, result). `understando note` is its only writer, and it redacts secrets. While the mode is on, the agent notes each user prompt. An optional prompt hook (Claude Code `UserPromptSubmit`, and the Codex hooks file when the installed Codex has hooks) calls the same CLI, and only while the mode is on. `explain` turns the journal into the "Why it was built this way" level.

**Writes into the reviewed repo** go only to the branch `understando/<pr>-ready`: a drafted check after probe sees it go red, and trim's deletions. Never into the PR's own commits.

**Standalone first, mesh when present.** understando installs and works with no other skill pack. `references/working-rules.md` indexes its adapted copies of the reply rules, the subagent rules, the principles and the playbook steps that it uses, from pstack (Poteto Mode) and the Matt Pocock skills (MIT, see `THIRD_PARTY_NOTICES.md`). When an original skill is installed, understando routes to it (`understando routes`). `doctor` reports a missing optional skill, or an adapted copy older than the installed original, as a mention.

**Works with:**
- **Poteto Mode (pstack):** when it is active, it owns the reply style, the subagent rules and autonomy. understando keeps its exceptions: discover, claim wording and waivers stop for the user. The principle skills and the review skills (interrogate) replace the adapted copies.
- **impeccable:** its snapshots import as evidence (`understando import impeccable`), and its UI checks serve as e2e drivers for a web surface.
- **Matt Pocock skills:** grilling runs the question rounds of discover; tdd, to-spec, domain-modeling, code-review and handoff replace their adapted copies.
- **The Lean skill (lean-formal-feedback-loop):** formalize routes tier 5 work to it, and its proofs import as Lean evidence.

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

## Share a review

`understando publish <pr>` writes the explainer, `trust-map.json`, `pr-section.md` and a README to the orphan branch `understando/<pr>-review` of the reviewed repo, after a clear yes. It never writes the journal, discover, history, CI or key files, and the branch has no `.github/`, so no CI runs. A reviewer opens it with one line:

```bash
git fetch origin understando/489-review && git worktree add /tmp/review-489 FETCH_HEAD && open /tmp/review-489/explainer.html
```

Or `understando open 489`. `publish --feedback` sends a reviewer's confusion rows back to `feedback/<reviewer>.jsonl` on the branch. The details are in commands/publish.md.

## Machine config

`~/.understando/config.toml` holds `ve_runtime`, the visual-explainer runtime (an Artifacture checkout). setup asks for it once; doctor checks that it has `visual-explainer-mdx/components.tsx`, `scripts/artifacture.mjs` and Playwright. `UNDERSTANDO_VE_RUNTIME` overrides it for one command. The formal steps find java at `$JAVA_HOME/bin/java` or Homebrew's `/opt/homebrew/opt/openjdk/bin/java` without a PATH edit, and TLC at `~/.understando/tools/tla2tools.jar`.
