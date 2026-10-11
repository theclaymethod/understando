# open

For the reviewer, and for each stop that links to the explainer: `understando open [<pr>] [--level L] [--anchor A] [--no-open]`.

## Open the page

`understando open` opens `explainer.html` of the run with `open` (macOS) or `xdg-open` (Linux, with a display). With `--no-open`, with no display, or with `UNDERSTANDO_NO_OPEN` set, it prints the file path and the `file://` URL. Each open writes one row to `$R/opened.jsonl`.

The anchors are stable. The levels are `#story`, `#why`, `#loop`, `#changed` (`--level change` works too), `#promises`, `#verifiers`, `#unclaimed`, `#tradeoffs` and `#glossary`. The merge verdict is `#merge`, a promise is `#promise-<id>` and a claim is `#claim-<id>`. `--anchor G3` gives `#promise-g3`, and `--anchor C15` gives `#claim-c15`.

## The reviewer's path

1. **Find the page.** `understando open <pr>` uses the local run of the PR when it exists. Else it fetches the review branch `understando/<pr>-review` from origin into a read-only worktree (`publish.fetch_review_branch`), and opens its explainer.
   - **Done when** the page is open, or the CLI printed why it cannot fetch it.
2. **Ask one question.** "How do you want to read it?": walk me through it (recommended), or ask about one part.
3. **Walk through it.** `understando open <pr> --teach` is the same teach stop as the author's ([../references/adapted/teach.md](../references/adapted/teach.md)). Each turn gives one part of the page, a few sentences, and one question.
4. **Record what is not clear.** `understando open <pr> --ask "<question>"` writes a `confusion` row with the anchor that is open to the reviewer's own run journal. The author sees the rows only after the reviewer runs `understando publish --feedback`.
