<!--
adapted-from: skills/engineering/code-review/SKILL.md
source: mattpocock-skills
source-version: 1.3.1
license: MIT, Copyright (c) 2026 Matt Pocock. See THIRD_PARTY_NOTICES.md.
original-skill: code-review
-->
# Two-axis code review

Review the diff between `HEAD` and a fixed point on two axes. Run each axis in its own subagent so they do not pollute each other's context. Use a reviewer of a different model family from the author, per subagents.md.

- **Standards.** Does the code follow this repo's documented coding standards?
- **Spec.** Does the code do what the originating issue or spec asked?

## Process

1. **Pin the fixed point** (commit, branch, tag, `main`, `HEAD~5`). Ask if none was given. Capture `git diff <fixed-point>...HEAD` (three dots, against the merge-base) and `git log <fixed-point>..HEAD --oneline`. Confirm the ref resolves with `git rev-parse` and the diff is non-empty. Done when: both commands run clean.
2. **Find the spec.** In order: issue references in commit messages, a path the user passed, a spec file under `docs/`, `specs/` or `.scratch/` matching the branch. If none exists, ask. If the user says there is none, skip the Spec axis and say so.
3. **Find the standards sources.** Anything documenting how code is written (`CODING_STANDARDS.md`, `CONTRIBUTING.md`). Add the smell baseline below. A documented repo standard overrides the baseline. Each smell is a judgment call. Skip anything tooling enforces.
4. **Run both subagents in parallel.**
   - Standards brief: "Report per file or hunk (a) each place the diff violates a documented standard, citing file and rule, and (b) each baseline smell, naming it and quoting the hunk. Separate hard violations from judgment calls. Skip anything tooling enforces. Under 400 words." Include the diff command, commit list, standards files and the full smell baseline.
   - Spec brief: "Report (a) requirements that are missing or partial, (b) behavior in the diff that was not asked for, (c) requirements that look implemented but look wrong. Quote the spec line for each finding. Under 400 words." Include the diff command, commit list and spec.
5. **Aggregate.** Present `## Standards` and `## Spec` side by side, verbatim or lightly cleaned. Do not merge or rerank. End with the finding count per axis and the worst issue within each axis.

Reporting the axes apart stops one from masking the other. Code that follows every standard can implement the wrong thing. Code that does what the issue asked can break conventions.

## Smell baseline (name, then fix)

- Mysterious Name. A name that hides what the thing does. Rename it.
- Duplicated Code. The same logic shape in several hunks. Extract it.
- Feature Envy. A method that reaches into another object's data more than its own. Move it to the data.
- Data Clumps. The same few fields travel together. Bundle them into a type.
- Primitive Obsession. A primitive stands in for a domain concept. Give it a small type.
- Repeated Switches. The same cascade on one type recurs. Use polymorphism or one shared map.
- Shotgun Surgery. One change forces edits across many files. Gather what changes together.
- Divergent Change. One module changes for several unrelated reasons. Split it.
- Speculative Generality. Abstraction for needs the spec lacks. Delete it.
- Message Chains. Long `a.b().c().d()` walks. Hide the walk behind one method.
- Middle Man. A unit that only delegates. Call the real target.
- Refused Bequest. A subclass ignores most of what it inherits. Use composition.

Done when: both axis reports are aggregated with counts, or the Spec axis is skipped with a stated reason.
