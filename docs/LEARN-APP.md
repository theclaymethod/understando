# understando learn: the learn app

## Purpose

The learn app helps a developer learn a PR and judge how well the author verified the PR. It pairs the pre-generated content of one run folder with a live tutor.

- `explain` still makes `explainer.html` and the PR-body section.
- `learn` starts one local binary for one run folder (`~/.understando/runs/<repo>/<pr>/`) and opens the browser.

## Two tiers

| Tier | What | Who makes it |
|---|---|---|
| Fact | The trust map, the verdicts, the recorded control results, the chapters, the answer keys, and each server run | Tools, before or during the session |
| Guess | Tutor answers, "explain this snippet at my level", tutor shell output, Mermaid diagrams on request, the explain-it-back grade | A model, live |

**Hard rule:** live output never changes a verdict. The app never writes `trust-map.json`. The UI labels each live text "Model-generated" and "guess tier".

## Shape

```
learn/
  learn.sh            the `understando learn <run-dir>` entry
  e2e.sh              all learn tests, from one command
  hermetic-env.sh     the default --env-file for verifiers
  src/                the Rust binary (axum + tokio)
  web/                the UI (Vite + React + TypeScript), embedded into the binary
    scripts/compile-chapters.mjs   chapter MDX -> <run>/learn/chapters.json
    e2e/              Playwright tests, fake CLIs, the fixture run builder, the #489 smoke run
```

- The UI is a template. `npm run build` makes it one time, and rust-embed puts it into the binary.
- The per-PR content is data in the run folder: `trust-map.json` and `learn/chapters.json`.
- The chapter compiler runs with Node at explain time. The learner needs only the binary, git, a tutor CLI, and the toolchain of the reviewed repo for its verifiers.

## The server

- It listens on 127.0.0.1 only. It checks the Host header on each request. It refuses `sec-fetch-site: cross-site`. A POST must come from the app origin with a JSON body.
- It reuses a running server for the same run folder, and it picks a free port from 4190 to 4289.
- At start, it makes a private clone of the reviewed repo (`git clone --local --no-checkout`). It adds one scratch worktree at the PR head, in a new temp folder. The user's checkout is never a working directory. On exit (Ctrl+C or SIGTERM), it stops the active run and removes the worktree, the clone and the folder.
- One activity runs at a time: one tutor turn, one graded run or one grade.

## The tutor has a sandboxed shell

The tutor is a coding agent. It can read files, run tests, use `git diff`, edit files and plant bugs in the scratch worktree. An OS sandbox contains it. A tool ban does not.

| | Claude Code (default) | Codex |
|---|---|---|
| Call | `claude -p`, stream-json | `codex app-server --stdio`, JSON-RPC |
| Tools | Bash, Read, Grep, Glob, Edit, Write | its shell, with `shell_tool` on |
| Sandbox | `--settings` `sandbox.enabled`, `failIfUnavailable`, `allowUnsandboxedCommands: false`, no allowed domains, `denyRead` with the denied paths below | the permission profile `learn`: it extends `:read-only` (no network, no write), adds write for the worktree only, and adds `deny` for the denied paths below |
| Isolation | `--restricted`, `--setting-sources ""`, `--strict-mcp-config` with no servers, `disableAllHooks`, `--disable-slash-commands`, `--no-session-persistence`, `--permission-mode dontAsk` | each MCP server off (checked with `codex mcp list --json`), plugins, hooks, browser use, multi-agent, memories and web search off, `approval_policy=never` |
| Account | the learner's signed-in Claude account | the learner's Codex login. For Function-Health/function-intelligence: the `OPENAI_API_KEY` in `/Users/clayton/dev/function-intelligence/.env` |

- **Environment.** The server removes provider keys, agent session markers and secret-like names (`*_API_KEY`, `*_TOKEN`, `*_SECRET`, `*PASSWORD*`, `*_OP_REF`) from each child environment.
- **Codex key.** For function-intelligence runs, Codex gets an empty `CODEX_HOME` in the scratch folder and `cli_auth_credentials_store="ephemeral"`. The server sends the key in an `account/login/start` RPC. Thus, the key is in no environment variable and in no file that Codex writes, and the shell cannot see it in its environment. The server never prints the key.
- **Fail closed.** The doctor checks the OS sandbox (macOS `sandbox-exec`, Linux bubblewrap). When it cannot start, the Claude tutor gets Read, Grep and Glob only, and Codex gets a read-only sandbox with `shell_tool` off. The app never falls back to a shell without a sandbox.

### Denied paths

The tutor shell cannot read these paths. Both providers get the same list.

- The user's checkout of the reviewed repo, and each `.env*` file under it (`<checkout>/**/.env*`).
- Each `.env*` file under `/Users/clayton/dev/function-intelligence`, and the key file `/Users/clayton/dev/function-intelligence/.env`.
- `~/.codex`, `~/.claude`, `~/.ssh`, `~/.aws`, `~/.config/gh`, `~/.netrc`, `~/Library/Keychains` and `~/.docker/config.json`.
- `~/.gnupg`, `~/.npmrc`, `~/.pypirc` and `~/.kube`.
- Two canaries in the scratch folder: `canary/**/.env*` and `canary-dir/`.

**The Codex layer.** A second `sandbox-exec` profile around `codex app-server` does not work. macOS refuses a nested sandbox (`sandbox_apply: Operation not permitted`) when the outer profile has a deny rule, and Codex starts its own seatbelt for each command. Thus, the deny rules go into Codex's own seatbelt, as `deny` entries of a permission profile (`-c permissions.learn=...`, `-c default_permissions="learn"`). The thread and the turn set no sandbox field, so nothing overrides the profile.

**The Codex check.** Before each Codex turn, the server runs probes in the same `codex app-server` through `command/exec`, which sends no model request:

- A `cat` of each canary must fail.
- A `touch` outside the worktree must fail.
- A `cat` of a file in the worktree must work.
- A `cat` of the real key file must fail, when the file exists.

The server also checks that the thread reports no full access and no network. The server start and the doctor run the same probes. When one probe fails, the Codex shell is off for the session, and the doctor says why.

**The Claude check.** Claude Code applies `denyRead` in its own sandbox. No check without a model call exists for it. The e2e tests check that the server passes each path. `learn/web/e2e/sandbox-check.sh` checks the real denial with one live call.

### Why grading stays with the server

The tutor shell can edit the worktree, so its output can be wrong, and the tutor can change the code that a test checks. Thus, the tutor shell never decides a grade or a verdict.

- Before each graded run, the server resets the worktree: `git checkout --force`, `git reset --hard`, `git clean -ffdx`. Then it runs the `setup` steps, applies the recorded edits and runs the recorded argv and cwd from the trust map, under the recorded timeout. After the run, it resets the worktree again.
- The tutor asks for a graded run with one tag: `<understando-action kind="run-control" id="K16"/>` or `<understando-action kind="run-verifier" id="V19"/>`. The server takes each tag out of the visible text and compares it with the allowlist. The allowlist holds the control and verifier ids of the trust map that have a command. A tag can hold only the `kind` and `id` attributes. A refused tag shows as a refusal.
- The learner approves each proposal in the UI before it runs. The direct route `/api/run` takes only `kind` and `id`. A request with an `argv` field gets a 400.

## Exercises

| Kind | Graded by | Source |
|---|---|---|
| Predict, then run | the server run of the control: red or green | each control with a command |
| Trace it | code, against the steps of the answer key | `exercises` (kind `trace`) |
| Find the line | code, against the `code` refs of the claim | each claim with code refs |
| Close a gap | the server: the test must pass at the head, then fail on the planted bug | `exercises` (kind `close-gap`) |
| Explain it back | a model, against the answer key (guess tier) | each claim with `plain` text |

- In "predict, then run", a green result on a control means that the check cannot fail. The UI flags it.
- In "close a gap", the learner writes only the test file that the exercise names, through a server route. The server keeps the text in `my-work/close-gap.json` and writes it again after each reset.
- **Schema change.** The claims hold no trace steps and no test path, command or planted bug. Thus, `schema/trust-map.schema.json` has an optional `exercises` array for the kinds `trace` and `close-gap`. The other three kinds come from the claims and controls.

## The learner's record

`<run>/my-work/` holds `progress.json` (attempts, passes, runs), `close-gap.json` and `tutor-conversation.json`. Each write goes to a temp file and then a rename. The server saves a prediction before its run starts. `my-work/` and `learn/` stay out of git.

## Chapters and the Artifacture components

- `compile-chapters.mjs` reads `explainer.mdx`. When the file imports one MDX unit per chapter from `chapters/`, each `<Section>` of the entry is one chapter. Else the script splits the file at each top-level `<Section>`. Each JSON file that the explainer imports (the trust map, the resolved refs, `explain.json`) goes inline into each chapter that uses it, and `promiseAnchors(...)` becomes its value, because the app has no module loader. It runs Artifacture's preflight (diagram checks and code colours), then compiles each chapter to an MDX function body.
- The UI imports `visual-explainer-mdx/components.tsx` from `UNDERSTANDO_VE_RUNTIME` and runs each chapter with those components. They import cleanly outside the Artifacture export. The import needs three settings: an alias to the checkout, a React `dedupe`, and the Tailwind v4 Vite plugin for `global.css`. The checkout must have its `node_modules`.
- Build the UI against the checkout that the chapter MDX imports from. A chapter that names a component the build does not have shows an error, and the other chapters still show.
- Mermaid ships inside the app. A Mermaid block in a tutor answer shows as a diagram with the label "Model-generated".

## Provider and cost

- The learner picks Claude Code or Codex in the tutor panel. The default is the provider that the doctor finds ready. When both are ready, the default is Claude Code.
- The panel shows the account that each call bills to, the model and the shell state.
- The doctor sends no model request. It reports git, the worktree, the OS sandbox, both CLIs, the sign-in, the Codex tool isolation and the default Codex model (from `model/list`).

## Tests

- `learn/e2e.sh` builds the UI and the release binary. It runs Playwright on the fixture repo, with a fake `claude` and a fake `codex app-server` first on PATH. Then it runs the model-free #489 smoke run: start, load, one control, stop. Set `SKIP_489=1` to skip the smoke run.
- The fake CLIs model the sandbox and the read denial from the config that the server passes. `learn/web/e2e/sandbox-check.sh` checks the real sandbox with one live call. It tries a write in the worktree, a write in the checkout, the network, and a `cat` of a planted secret. It runs only with `REAL_SANDBOX_CHECK=1`.
