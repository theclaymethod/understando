# setup

Start this sub-command only on an explicit request from the user.

## A. Global setup

1. Run `understando setup` (or `bash $U/scripts/setup.sh`). The script is idempotent. It links the CLI into `~/.local/bin` and the skill into the four skill folders. It asks whether the optional skills go to the project or to the global skill folders (`--scope project|global`), and installs the Code Contracts skill. It puts `cc-check` in the npm cache through `npx`. It installs a missing pstack verification skill, asd-ste100 or visual-explainer. It ends with `doctor`.
   It prints the optional prompt hook (`hooks/user-prompt-submit.json`) and asks before it adds it to `~/.claude/settings.json`, or to `~/.codex/hooks.json` when the installed Codex has hooks. Never add the hook without the user's yes at run time.
   - **Done when** the last line is `doctor: every required piece is present`.
2. When a link step prints `refuse:`, another skill holds the name. Keep that skill. Report the path to the user and stop.
   - **Done when** each `refuse:` line is in your report, or no such line exists.
3. To check later without an install, run `bash $U/scripts/setup.sh doctor`.

## B. Per-repo setup

Run this part on the first use in a repo, and only after the user approves each item.

1. **Code Contracts.** Propose this line for the repo's `AGENTS.md`: "Use `$code-contracts` for `@cc` contracts. Check their syntax with `npx @spolu/cc-check@0.2.0 format`." Write it on a separate branch, as a patch for the author.
   - **Done when** the user approved the line and the patch exists, or the user declined.
2. **Web or mobile UI.** When the repo has a web or mobile surface, propose `E2E_TELEMETRY_DISABLED=1 npx e2e init` (tester-army). `init` asks for a model provider. Show that choice to the user, because agent steps cost money.
   - **Done when** the user approved and `init` completed with telemetry off, or the user declined.
3. **CLI, TUI or service.** Tell the user to start the create-verification-skill skill (`/pstack:create-verification-skill` in Claude Code). The user must start it, because that skill sets `disable-model-invocation`. It writes `.cursor/skills/verify-<app>/`.
   - **Done when** the command is in your reply.
