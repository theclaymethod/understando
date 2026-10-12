# The project-local verify skill

The verify skill lets the next agent drive the real app and prove a behavior. That agent reads it cold, mid-task, with no memory of the app. Write it in the working tree, as ordinary uncommitted files. The user commits it.

```text
.agents/skills/verify-<app>/
  SKILL.md               frontmatter, then Launch, Doctor, Drive, Evidence, Cleanup, Helpers
  features/README.md     the index: baseline preconditions, driving conventions, proof rules, the features
  features/<feature>.md  one file for each user-facing feature
.claude/skills/verify-<app> -> ../../.agents/skills/verify-<app>   (a relative symlink)
```

When the repo has a verify skill already (for example `.cursor/skills/verify-<app>/` from pstack), keep it. Add the missing feature files and the Verifier sections.

## SKILL.md

The frontmatter has `name: verify-<app>` and a `description` that names the app, the surface and when to use the skill. Without frontmatter, the skill does not register. Each section comes from the code:

- **Launch:** the exact start command, how to tell that it is ready (a log line, a port, a prompt), and its teardown. For a short-lived CLI, launch builds once, and each drive runs in its own process.
- **Doctor:** one read-only check: is this instance worth driving? The process is up, the build is right, the port is ours.
- **Drive:** the harness recipe with the real selectors and commands of this repo. Use stable handles (ARIA names, data attributes, prompt strings, routes), not coordinates.
- **Evidence:** what a drive keeps and where ([verifiers.md](verifiers.md)).
- **Cleanup:** stop only what launch started. Keep the evidence, and check that it is still at its place after cleanup.
- **Helpers:** each script that the skill ships is executable, and the skill body shows how to call it.

## The feature file

```markdown
# <Feature name>

<One paragraph: the behavior that the user sees.>

## Sub-features
- `<id>` <one line for each behavior>

## How to get to it (user POV)
- <each user entry point>

## Driving it with <harness>
Preconditions:
- <the state that a drive needs>

- **<Action>.** <What the user does.> Run `<exact command>`. <The observable result.>

## Gotchas
- <traps that waste or spoil a run>

## Verifier
- **Surface:** backend | frontend | llm.
- **Bar:** <the bar for this surface, from verifiers.md>.
- **Invariants:** <each one, with its author: user, or agent-picked>.
- **Verifiers that meet the bar:** <each one: the command, and each control as a `control.sh` command with its result>.
- **Verifiers that do not count:** <each one, and why: cannot fail, below the bar, not proven yet>.
```

## Worked example: wallet withdraw

The fixture app is a CLI: `python3 -m wallet withdraw BALANCE AMOUNT` prints the new balance, or refuses an overdraft with exit code 3.

```markdown
## Driving it with the wallet CLI
Preconditions:
- `python3 -m wallet --version` prints `wallet 1.0`.

- **Withdraw.** Run `python3 -m wallet withdraw 10 3`. Exit code 0, and stdout is `7`.
- **Refuse an overdraft.** Run `python3 -m wallet withdraw 10 11`. Exit code 3, and stderr holds `refused`.

## Verifier
- **Surface:** backend.
- **Bar:** a proof for the risky invariant; a contract, types or a property test for wiring.
- **Invariants:**
  - I1 (user): a withdrawal never takes the balance below zero.
  - I2 (agent-picked): a refused withdrawal leaves the balance unchanged.
- **Verifiers that meet the bar:**
  - Lean `withdraw_nonneg` with vector conformance: `$U/scripts/lean-check.sh --dir formal/lean --import Wallet withdraw_nonneg`, then `python3 -m pytest tests/test_conformance_wallet.py`.
    - Code control, red: `$U/scripts/control.sh --replace wallet/core.py 'if amount > balance:' 'if False:' -- python3 -m pytest tests/test_conformance_wallet.py`.
    - Model control, red on `withdraw_nonneg`: `$U/scripts/control.sh --dir formal/lean --replace Wallet.lean 'balance - amount' 'balance - amount - 1' -- $U/scripts/lean-check.sh --import Wallet withdraw_nonneg`.
  - The CLI e2e above: `.agents/skills/verify-wallet/helpers/drive withdraw`. Control, red (exit 0, not 3): the same code control, with the drive as the command.
- **Verifiers that do not count:**
  - `tests/test_core.py::test_withdraw_ok`: it stayed green on the deleted guard (cannot fail).
- I2 has no verifier yet. It stays at Backed until the user accepts it.
```
