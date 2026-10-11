<!--
adapted-from: skills/teach/SKILL.md
source: agent-guards
source-version: c86d619
license: MIT, Copyright (c) 2025 Matthew Lam. See THIRD_PARTY_NOTICES.md.
original-skill: teach
-->
# Teach: walk the user through a change

The teach stop helps the user build a mental model of the PR. After the walk-through, the user can explain the change to a colleague, reason about a new case and see the weak parts. `understando review <pr> --teach` (the author) and `understando open <pr> --teach` (the reviewer) give one turn at a time.

## The explainer comes first

The explainer page holds the story, the loop, what changed and the promises. Do not repeat the page in chat.

1. Each turn opens the next part of the page with `understando open --anchor <id>`: the story, then the loop, then what changed, then the weakest promise.
2. In chat, add only what the page cannot give. That is the answers to the user's questions, the code behind them, and a short check of what the user now understands.
3. When the user asks about a part that the page shows, open that anchor first. Then answer in three sentences or fewer.
4. When no page exists, build it first (`understando explain --html`), or tell the story in chat.

## Rules

- **Depth over breadth.** Pick the two to four ideas that matter most for this PR: the promises and the riskiest claims, weakest first. Stay on them until the user understands them. Keep the rest for later.
- **Role before name.** Say what a part does and what it acts on. Then give its name, as a ref.
- **One run, end to end.** Give one concrete walk-through: who acts, what it calls, what data moves, and what state changes.
- **The code is the source of truth.** Trace the real code path before you explain it. Do not fill a gap from a name, a comment or a familiar pattern. When you cannot check a behaviour, say that it is unknown.
- **Keep three things apart.** The existing behaviour, the change that the PR makes, and what is not known.
- **Each guarantee has its check.** When you say that a claim is guaranteed, name the claim and its check in a ref: `(ref: C15, V19)`. The check must catch its planted bug. A Backed claim is backed, not guaranteed. A Gap claim is unknown.
- **Code by refs.** Show code with `understando snippet <path>::<symbol>`, never as pasted code.
- **Start small.** Give a small, complete first answer. Then follow the user's questions. Ask one short question at the end of each turn. Do not give a quiz or a lecture.
- **A few sentences a turn.** Each turn has a few sentences, the line "I opened <part>", and one question or a choice.

## The reviewer's questions

For a reviewer, `understando open <pr> --ask "<question>"` records the question as a `confusion` row with its anchor in the reviewer's own run journal. The author sees it only after the reviewer runs `understando publish --feedback`.

Teaching does not give permission to change the code.
