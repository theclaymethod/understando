# The verify skill and its spec

`understando create` writes a project-local verify skill from a spec that you write after the interview. The skill is for the next agent: it reads it cold, mid-task.

## The tree

```text
.agents/skills/verify-<app>/
  SKILL.md                 frontmatter (name, description), then Launch, Doctor, Drive, Evidence, Cleanup, Helpers
  helpers/verify           executable: launch | doctor | drive <feature> | cleanup | prove <feature>
  features/README.md       the index: baseline preconditions, proof and skip reporting, the entry contract, the features
  features/<feature>.md    one file for each user-facing feature
.claude/skills/verify-<app> -> ../../.agents/skills/verify-<app>    (a relative symlink)
```

A repo that has a verify skill already (for example `.cursor/skills/verify-<app>/` from create-verification-skill) keeps it: `create` adds the missing feature files, the Verifier sections and, when the skill has none, `helpers/verify`.

## The feature file

```markdown
# <Feature name>

<One paragraph: the user-visible behaviour.>

## Sub-features
- `<id>` <one line for each behaviour>

## How to get to it (user POV)
- <each user entry point>

## Driving it with <harness>
Preconditions:
- <the state a drive needs>

- **<Action>.** <What the user does.> Run `<exact command>`. <The observable result.>
- **Proof.** Run `.agents/skills/verify-<app>/helpers/verify drive <feature>`. <What it keeps as evidence.>

## Gotchas
- <traps that waste or invalidate a run>

## Verifier                     (understando writes this section from its store; do not edit it by hand)
- **Surface:** frontend | backend | llm | other.
- **Bar:**
  - frontend: a real-browser e2e of the user path, with a recorded video and screenshots.
  - backend: **Formal** (Lean or TLA+ with conformance, for a risky invariant); **Code Contracts** (a `@cc` contract states the invariant, and a check with a control proves it); **types, import rules and property tests**, for wiring.
  - llm: a recorded eval with a frozen judge or labels, and a degraded variant that must score worse.
- **Invariants:** each one with its author: the user's, or agent-picked and not accepted yet.
- **Verifiers that meet the bar:** each one with its command, its controls and what made it fail.
- **Verifiers below the bar or not proven yet**, and **verifiers that do not count** (cannot fail, failing).
- **Rule:** every verifier has a control that must make it fail.
```

## The spec (create.spec.json)

```json
{
  "app": "wallet",
  "description": "Names the app, the surface and when to reach for the skill.",
  "intro": "One paragraph for the top of SKILL.md.",
  "launch": {"text": "...", "ready": "how to tell it is ready"},
  "doctor": {"text": "one read-only check: is this instance worth driving?"},
  "drive": {"harness": "the name of the harness", "text": "..."},
  "evidence": {"text": "what a drive keeps, and where"},
  "cleanup": {"text": "kill only what launch started; keep the evidence"},
  "preconditions": ["the baseline state of every drive"],
  "helper": {"launch": "bash", "doctor": "bash", "cleanup": "bash", "drive": {"<feature>": "bash: exits 0 only when the end state holds"}},
  "features": [{
    "id": "withdraw", "name": "Withdraw money", "summary": "...", "surface": "backend", "paths": ["wallet/"],
    "sub_features": [{"id": "...", "text": "..."}], "entry_points": ["..."], "preconditions": ["..."],
    "steps": [{"label": "...", "action": "...", "command": "...", "result": "..."}], "gotchas": ["..."],
    "evidence": ["withdraw-ok.txt"],
    "control": {"description": "...", "edits": [{"op": "delete-line", "path": "wallet/core.py", "symbol": "withdraw", "match": "if amount > balance:"}]}
  }]
}
```

The helper bodies run in bash from the repo root, with `$EVIDENCE` (the evidence folder, `$VERIFY_EVIDENCE_DIR`) and `$STATE` (scratch state, `$VERIFY_STATE_DIR`). A drive writes its proof to `$EVIDENCE` and exits non-zero when the end state does not hold, so a planted bug can make it fail. The drive of each feature becomes an e2e check in the store, and its `control` becomes the control of that check.
