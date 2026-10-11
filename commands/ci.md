# ci

The repo's reviewed CI profile for one PR. `understando ci` reads repo files as data and runs nothing. It writes `$R/ci.json`. `review` runs it. `probe`, `close` and `trim` refuse a command that is not in the approved profile.

Each stop of this playbook ends with one question to the user. Ask it as [Asking the user](../references/working-rules.md#asking-the-user) tells you: the situation, a Next line, and numbered options.

## Steps

1. **Derive.** Run `understando ci [--pr N]` in the clone of the reviewed repo. It reads at the PR head:
   - `AGENTS.md` of the root and of each touched project: the lines that name the CI profile, and each fenced command. A command that only a doc names never runs.
   - `catalog.toml`, when it exists: the projects that the PR touches. A changed path outside each project fails open to every project.
   - `.github/workflows/*.yml`: each `run:` step of each job that runs on a pull request and names a touched project, or names no project. Each command has its `file:line`. A step that needs CI context (an expression, a secret, OIDC, a push to main) is in `excluded` with the reason.
   - The formal tools, when `<project>/formal/` exists at the ready-branch tip: `lake build`, the TLC checks, and the vectors checks.
   - **Done when** it prints the command list and writes `ci.json`.
2. **Ask the user once.** Run `understando ci --question --json`, and relay its `prompt`. It gives the number of commands and the reason for that number. Then it gives the options: approve all (recommended), show the list, approve only the main project, and something else. When the user picks "Show the list", show the output of `understando ci` with the source of each command. A command marked "new in this PR" comes from the PR's own workflow change, not from reviewed CI.
   - **Done when** the user picked an option.
3. **Approve.** Run the approval only after the user picked it in this conversation: `understando ci --approve`, or `understando ci --approve --project <name>`. A project approval covers only the commands that run in the folder of that project. The gate refuses each other command. The approval holds the digest of the approved commands. When those commands change, the approval stops, and the user must approve again.
   - **Done when** `understando ci` prints `approved by the user`.

To check one command, run `understando ci --check-argv <argv>`. It says which command allows it, and whether the user approved that command.
