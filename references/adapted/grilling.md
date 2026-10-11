<!--
adapted-from: skills/productivity/grilling/SKILL.md
source: mattpocock-skills
source-version: 1.3.1
license: MIT, Copyright (c) 2026 Matt Pocock. See THIRD_PARTY_NOTICES.md.
original-skill: grilling
-->
# Grilling

Interview the user relentlessly until you reach a shared understanding. Map the work as a design tree: every decision branches into the decisions that hang off it.

Work the tree in rounds. The frontier is every decision whose prerequisites are already settled, meaning the questions you can ask now without guessing at answers you have not heard. Ask the whole frontier in one round. Number each question and give your recommended answer. Then wait for the user's answers before the next round.

Format a round like this.

```
Q1 - <question title>: <question body, may be several paragraphs, including multiple choices>

Recommended: <your recommended answer>

---

Q2 - <question title>: <question body>

Recommended: <your recommended answer>
```

Each round the user answers reshapes the tree. Settled decisions push the frontier outward and unblock dependent questions. Recompute the frontier and ask the next round. A question that depends on another question still open in this round belongs to a later round.

Finding facts is your job, never the user's. When a frontier question needs a fact from the environment (files, tools, the code), dispatch a subagent to find it and do not ask the user. Do not block on it: only the questions downstream of the exploration wait for its report. Ask the rest of the frontier now. The decisions are the user's. Put each to them and wait.

Done when: the frontier is empty, every branch of the design tree is visited, and no assumption stays unspoken. Do not act on the result until the user confirms you reached a shared understanding.
