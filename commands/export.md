# snippet and export

The references that an explainer needs. understando writes no page: visual-explainer renders the data.

## Never paste code

Do not type code, line numbers or a GitHub URL into the store. Write a code ref: `{"path", "symbol"}`, with `"match"` and `"context"` for a part of a symbol, or `"part"` (`signature`, `body`). A line range `{"path", "start", "end"}` is the last choice: it drifts.

- **Preview a ref.** `understando snippet <path>::<symbol> [--match TEXT]` prints the lines, their numbers and the permalink at the commit where the ref resolves: the store head, or the understando branch for a file that only the branch has. `understando snippet <path> --lines A-B --suggest` prints the anchor of a range.
- **The guard.** The export refuses text in the store that is a copy of two or more lines of code at the head.

## Steps

1. **Export.** Run `understando export [--base REF]`. It writes `$R/export/trust-map.json` (the trust map of the visual-explainer card: the invariants with their author, the claims, the verifiers, the controls, the flags; and the features, the mutation runs with the kill matrix, the last proof and the last upkeep pass as extras) and `$R/export/refs.resolved.json` (each code ref resolved, with its permalink, and with `--base` its diff line marks; the patch of each control; the derived block with the strength, checks and bar of each claim and whether the checks can catch a bug).
   - **Done when** it prints the two paths. Fix a ref that does not resolve with `understando snippet`.
2. **Render.** Hand the two files to visual-explainer.
   - **Done when** the user has the page or the paths.
