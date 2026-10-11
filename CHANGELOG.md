# Changelog

## Unreleased

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
