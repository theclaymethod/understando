# publish: share a review

The user starts `publish`. It writes outside this machine, so it always asks for a clear yes first. The question names the remote, the branch, the commit message and each file.

## Share a review

The author publishes the explainer to an orphan branch of the reviewed repo:

```bash
understando publish 489 --dry-run   # the checks, the question and the file list
understando publish 489             # asks; on a yes, commits and runs `git push origin understando/489-review`
```

A reviewer opens it with one line:

```bash
git fetch origin understando/489-review && git worktree add /tmp/review-489 FETCH_HEAD && open /tmp/review-489/explainer.html
```

Or with understando: `understando open 489`. It keeps a read-only checkout at `~/.understando/review-cache/<repo>/489`.

A reviewer sends back the points that confused them. Each one is a journal row of kind `confusion` (`understando note confusion "..."`). Then:

```bash
understando publish 489 --feedback   # asks; on a yes, appends the rows to feedback/<reviewer>.jsonl on the branch
```

The author's review reads the feedback rows as signals.

## What the branch holds

- `explainer.html` and the local files it links;
- `trust-map.json`;
- `pr-section.md`;
- `README.md`, which tells how to open the review;
- `feedback/<reviewer>.jsonl`, when a reviewer sent feedback.

The branch never holds `journal.jsonl`, `discover.json`, `history/`, `ci.json`, `review.json`, `my-work/` or a key file. It never holds `.github/`, so no CI runs on it. It shares no history with the code.

## Rules

1. **Plumbing only.** publish writes blobs, a tree and a commit with git plumbing and a temporary index. The working tree, the index and HEAD of the reviewed repo do not change.
2. **Normal commits.** Each update is one commit on top of the remote tip, with a message such as `Review of 3fb72db3: Formal 5, Proven 24, Backed 9, Asserted 3, Gap 2`. When the remote branch moved, publish fetches it and commits on top. It never force-pushes.
3. **Refusals.** publish refuses when:
   - the explainer is stale: `explain.stamp.json` does not match the map head, the trust-map hash, `explainer.mdx` or `pr-section.md`, or `explainer.html` is older than `explainer.mdx`. Run `understando explain`, then export the HTML again;
   - the no-hand-copy guard finds pasted code;
   - a published path, or a code ref in the trust map, matches `secret_paths`, or a file holds a key-like string;
   - the tree would hold `.github/`.
4. **The yes.** On a terminal, publish asks. An agent asks the user the printed question, then passes the answer as `--answers FILE` with `{"answer": "yes"}`. Publish writes only after a yes.
