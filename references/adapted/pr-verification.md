<!--
adapted-from: skills/poteto-mode/playbooks/opening-a-pr.md and skills/poteto-mode/playbooks/shipping.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: poteto-mode
-->
# PR verification

The verification parts that `understando ready` feeds. The caller chooses the PR state and the forge.

## Description

A PR body is a briefing, not a lab notebook. A reviewer who has the diff learns why the change exists, what is out of scope and how you proved it works. Keep the body short enough that the squash commit body stays under about 40 lines. Use these sections in order and drop any that has nothing to say.

- `## Why`. The intent and approach in one or two short paragraphs. No SHAs, no rebase history.
- `## Scope`. Bullets naming real symbols and paths. State what is in and out only where the boundary matters.
- `## Tradeoffs`. Only the rejected alternatives a reviewer would otherwise ask about.
- `## Blast Radius`. One to three sentences on who or what the change touches and why it is safe or risky.
- `## Verification`. Each real run path and its outcome. For a performance change, one primary number as `before to after` with its unit. Link the artifact directory for the rest. Leave out methodology recitals, lane recitals and metric tables.

Attach videos or screenshots when they prove a claim. Put long evidence in a linked artifact.

## Size

Prefer five narrow PRs to one large one. Rebase onto trunk before substantial stack work.

## Independent verdict per PR

- Verify each PR with a subagent that did not write the code, one subagent per PR, each exercising the real surface against parent versus head.
- Each returns `PASS`, `PASS+NOTES` or `FAIL` and posts that verdict on its own PR. Safe means a verdict from an agent that did not write the code. A green CI run is not a verdict. An approving bot review is not a verdict.
- Land only the contiguous verified run from the bottom of a stack. Walk up from the lowest unmerged PR and stop at the first one without `PASS` or `PASS+NOTES`. A verified PR above an unverified one is not landable. Report the ceiling as a PR number and what breaks the chain.

## A verdict must still describe the patch

- Record the verdict head SHA, base SHA and the stable `git patch-id` of the base-to-head diff.
- A rebase or base retarget rewrites SHAs and can invalidate a verdict without touching a check. Before landing, compare the recorded patch-id with the current one.
- If the patch is unchanged, keep the code verdict and rerun mergeability and CI at the current head. If it changed, reverify. Matching commit messages or a green check from an older SHA is never a substitute.

Done when: each PR has a verdict from a non-author, the verdict's patch-id matches the current patch, and the report names the ceiling.
