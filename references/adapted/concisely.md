<!--
adapted-from: skills/concisely/SKILL.md
source: agent-guards
source-version: c86d619
license: MIT, Copyright (c) 2025 Matthew Lam. See THIRD_PARTY_NOTICES.md.
original-skill: concisely
-->
# Concise reports

The user's attention is the scarce resource. Report the parts of the work that matter, not each thing that you did.

- **Lead with the outcome.** Say first what changed, what passed, or what the state is now.
- **Plain names in prose.** Name a claim by its short plain sentence or its promise. Name a check by what it checks, and a commit by what it did. Give IDs, SHAs, paths and line numbers only in a trailing `(ref: ...)` part, in `--verbose` output, or in JSON fields. A reviewer does not know what C15 or V19 is.
- **Evidence for each claim.** Each statement that something works names the check or the run that shows it.
- **Prioritise.** Give the most important points and decisions. When a list has more than three items, name the top three and give the count. The user asks for more when they want it.
- **Call out what matters.** Say each decision that the user must make, each blocker, each uncertainty and each residual risk.
- **Speak as to a colleague.** Say who does what. Do not use stock phrases or abstract words that the reader must decode.
- **Depth goes elsewhere.** Put supporting detail in the explainer, a log file or `--verbose`. In chat, link to it.
