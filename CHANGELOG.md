# Changelog

## Unreleased

- The derived page text passes the STE gate and the copy rules. The labels "No action:", "Low risk: skim", "It only removes lines" and "Read these first" are now full sentences of 5 words or more. The derived text calls an invariant of the user "accepted", because the STE lint counts the old word as a synonym of "check". A merged claim keeps each source as its own sentence (`regroup.join_sources`). `commands/explain.md` no longer suggests a "Why this matters" aside.
- The test-isolation guard (`scripts/testguard.py`). Each script imports it first. A test run has `UNDERSTANDO_TEST=1` or a Playwright worker marker. In a test run, an audit hook refuses each write outside `UNDERSTANDO_TEST_ROOT`: each open for write, rename, replace, remove, mkdir and rmtree. It also refuses each read of the real `~/.understando`, except in a read-only verb (help, signals, menu, routes, snippet, `mode status`, `lock status` and the `config.py` sub-commands). A refusal stops the process with "understando test guard: ...", and an `except OSError` cannot hide it. The learn app refuses a `my-work` write outside the test root in the same way.
- Out of a test run, `review` refuses a real run folder when the `gh` on PATH is in a temp folder or a test fixture folder. The error names that `gh`.
- `tests/isolate.sh`: each test script sources it first (tests/*.sh, tests/formal/e2e.sh, learn/e2e.sh and learn/web/e2e/*.sh). It sets the guard, the test root and `TMPDIR`. It sets `UNDERSTANDO_HOME` and `UNDERSTANDO_RUNS` under its own `mktemp -d`. Its self-check fails the suite when one of them is in the real `~/.understando`. The Playwright config sets the same variables. `tests/isolate-e2e.sh` plants writes outside the root and a review with a fake `gh`. `tests/e2e.sh` and `learn/e2e.sh` compare the sha256 of the real #489 run files before and after the suite.
- Copy rules (`references/copy-rules.md`, data in `references/copy-rules.json`): the CLI says what happens, once, in the place where it applies. A prompt that holds a reassurance, a slogan, a stock word, a fragment sentence of 4 words or fewer, or a sentence that repeats does not render (`prompt.banned_copy`). `doctor` flags the same phrases in the docs (`copy-banned`). The "Something else" option has the label "Something else" and one fixed line.
- asd-ste100 is required, with no adapted copy: the agent applies it while it writes each text that a reader sees. `scripts/ste.py` runs its lint as a gate on the prompt render, on `map` and `validate.py` (claims, plain text, names, promises), on `discover answer`, on `close` wording, on the PR section and on the README of `publish`. `understando routes` shows it for every verb, and `doctor` flags it when it is missing.
- A claim holds parts, one for each statement, each with its own checks. A part is as strong as its strongest check; a claim is as strong as its weakest part. A check that missed its bug is a flag with an action, not a score. Each TLA+ property is its own check (`regroup.py split_checks`, the `split:` lint).
- Evidence bars for each surface (frontend, backend, llm, other): `references/evidence-bars.md` is their only source. The page, the PR section, the review lines, the ready gate 1, close and publish use them. doctor flags a doc that restates a bar.

- The review ontology: promise -> claim -> check (`scripts/onto.py`). A claim lists its checks (`claims[].checks`, `schema_version` 2), and a merged claim keeps `legacy_ids` and `parts`. A claim is as strong as its weakest check, and its card names that check with its action. `map` writes the new shape, prints the grouping lint (`merge:` and `budget:` lines) and refuses a missing plain name. understando reads the old shape for one release.
- The schema check refuses a claim with no checks, a check that no claim lists, and a claim in more than one promise.
- Plain names: the agent writes the name of each promise, claim and check. doctor flags a cut of the plain text, a path or a tool name.
- `understando coverage` records the changed files that each check runs. A claim covers a file when it cites or names the file. It also covers a file that one of its checks runs or that one of its controls edits.
- The unclaimed level leads with the risky files. Its "what we broke" lines are full sentences.
- `close --add-claim <file>` drafts a claim for a file, attaches the checks that run it, and offers a check. close can fix one weak check of a claim (`fix-check`, `drop-check`).
- `scripts/regroup.py` joins old claims into fewer claims from a proposal, and prints the safety proof.

- understando is a mode with one CLI, `bin/understando`.
- The verbs are map, discover, probe, formalize, import, close, trim, explain, learn (paused), ready, build, setup and doctor. The mode verbs are signals, menu, routes, mode and note.
- The verification ladder (tiers 1 to 5) and the verdict Formal. Proven and Formal need a stated claim or a user-confirmed invariant.
- The intent ledger `journal.jsonl`, the level that tells why the author made each choice, and the ready checklist.
- Adapted copies of pstack and Matt Pocock skill text under `references/adapted/` (MIT, see THIRD_PARTY_NOTICES.md).
- Deprecated: `controls` (now `probe`) and `rerun` (now `map`). Both aliases print the new verb. They go away in the next release.
- The arguments decide: `/understando review 489` runs review, and `/understando 489` is `review 489`. Only a bare invocation shows the menu.
- Each stop ends with one question: at most 5 situation lines, a Next line (scope, cost, time, writes), and at most 4 numbered options. `review`, `menu`, `ci --question` and `close --next` give it as `prompt` in `--json`. `menu --all` adds the verb table.
- review chains its steps into four stops: map + probe on the changed code, close (one claim per question), trim, and ready + explain.
- A possible bug whose code changed on the ready branch asks for a re-check (map + probe), not for discover.
- `ci --approve --project NAME` approves only the commands of one catalog project.
- Run state lives under `~/.understando/runs/<repo>/<pr>/`, never in a git repo. Every verb refuses a run folder inside one, and doctor flags tracked run output. understando's repo no longer tracks `runs/`.
- `publish <pr>` shares a review on the orphan branch `understando/<pr>-review` after a clear yes; `publish --feedback` sends a reviewer's confusion rows back. `fetch_review_branch()` gives `open` a read-only checkout.
- setup pins `ve_runtime` in `~/.understando/config.toml` and prints the PATH line for `~/.local/bin`. java is found from `$JAVA_HOME` or Homebrew's openjdk without a PATH edit.
