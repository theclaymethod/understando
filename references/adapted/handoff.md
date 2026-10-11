<!--
adapted-from: skills/productivity/handoff/SKILL.md
source: mattpocock-skills
source-version: 1.3.1
license: MIT, Copyright (c) 2026 Matt Pocock. See THIRD_PARTY_NOTICES.md.
original-skill: handoff
-->
# Handoff

Write a handoff document summarising the current conversation so a fresh agent can continue the work. Save it to the operating system's temporary directory, not the current workspace.

- Include a "suggested skills" section naming the skills the next agent should load.
- Reference specs, plans, decision records, issues, commits and diffs by path or URL. Do not duplicate their content.
- Redact sensitive information: API keys, passwords, personal data.
- If the user passed arguments, treat them as the focus of the next session and tailor the document to it.

Done when: a fresh agent can name the next action, the open claims and the files to read, from the document alone.
