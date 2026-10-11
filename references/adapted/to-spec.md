<!--
adapted-from: skills/engineering/to-spec/SKILL.md
source: mattpocock-skills
source-version: 1.3.1
license: MIT, Copyright (c) 2026 Matt Pocock. See THIRD_PARTY_NOTICES.md.
original-skill: to-spec
-->
# Claims as a spec

Turn what the conversation and the code already established into a spec. Do not interview the user. Synthesize. Publish where the caller says (a file, an issue tracker, a PR section).

## Process

1. **Explore the repo** if you have not. Use the project's glossary vocabulary and respect decisions recorded in the area you touch. Done when: you can name the modules involved.
2. **Sketch the seams** where the feature is tested. Prefer existing seams. Use the highest seam possible. Propose a new seam at the highest point you can. Fewer seams is better, and the ideal is one. Confirm the seams with the user. Done when: the user agrees to the seams.
3. **Write the spec** with the template, then publish it.

## Template

- **Problem Statement.** The problem from the user's perspective.
- **Solution.** The solution from the user's perspective.
- **User Stories.** A long numbered list in the form "As an <actor>, I want a <feature>, so that <benefit>". Cover every aspect of the feature.
- **Implementation Decisions.** Modules built or modified, their interfaces, technical clarifications, architectural decisions, schema changes, API contracts, specific interactions. Include no file paths or code snippets, since they go stale. Exception: a snippet from a prototype that encodes a decision more precisely than prose (a state machine, reducer, schema, type shape). Trim it to the decision-rich part and say it came from a prototype.
- **Testing Decisions.** What makes a good test (external behavior only), which modules are tested, prior art in the codebase.
- **Out of Scope.** What the spec leaves out.
- **Further Notes.** Anything else.

Done when: every section is filled or dropped on purpose, and the seams section matches what the user confirmed.
