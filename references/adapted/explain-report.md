<!--
adapted-from: skills/explain-report/SKILL.md
source: agent-guards
source-version: c86d619
license: MIT, Copyright (c) 2025 Matthew Lam. See THIRD_PARTY_NOTICES.md.
original-skill: explain-report
-->
# The content rules of the explainer

understando takes only the content rules of explain-report. The explainer keeps its own pipeline: MDX from the trust map, exported to HTML by the visual-explainer runtime.

- **Lead with the mental model or the decision.** The first screen says whether the reviewer can merge, and why.
- **Evidence for each claim.** Each statement links to the check, the run or the code ref that supports it.
- **Verified, inferred and unknown stay apart.** A Proven claim, a Backed claim and a Gap claim look different. The page says which is which.
- **Depth goes behind details.** Supporting detail waits in a collapsed block, after the main explanation.
- **A visual only when it helps.** Use the simplest form that makes a relation clear: a flow, a comparison or a before-and-after view.
- **Readable without JavaScript.** The text, the tables, the verdicts and the code refs show as static HTML. Scripts add only toggles, deep links and motion.
