---
name: understando
description: Help a developer decide where to spend review time on a change by tracing a consequential assumption to the user outcome and the evidence that would verify it.
license: MIT
---

# Understando

Answer the reviewer’s question: **What deserves my attention here?**

Read the change and follow it through a real user journey. Identify the outcome the user expects and where that expectation came from. Use whatever evidence the project has. A ticket can establish a promise; a recording can show what actually happened. When the intended outcome is uncertain, say what you inferred.

Find the assumption that matters most if it is wrong. Trace it to the procedure that decides the outcome. Compare it with what the available verification actually observed, on which revision, and under which conditions. Give priority to a plausible failure that would affect users, survive a rollback, or go unnoticed. If the checks already settle the consequential questions, cite the evidence and finish.

Lead with the user consequence. Point to the deciding code and the relevant assertion or observation. Use PStack or an existing project check to resolve the uncertainty when possible. If a gap remains, give the smallest scenario that distinguishes success from failure. Ask the developer only when their judgment would change the expected result.

For example, one click enqueues one invitation, but a retry can still deliver two emails. Follow the retry through delivery and count distinct messages attributable to that click after processing settles. A green enqueue check establishes only the queue behavior.

When asked to sync a spec, update the affected clause and its links to verification. Keep each claim within the scope its source supports. If there is no spec, draft the smallest supported clause. An E2E assertion, an eval, or a formal property can each supply evidence for it.
