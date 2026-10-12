# Changelog

## The lean cut

understando is now a light, markdown-first skill after the model of pstack's verification skills, with our preferences for what counts as a verifier and which tools to use. SKILL.md is a router to `modes/`, `references/` and thin shell wrappers in `scripts/`. It keeps no store and no state between runs, and it writes into the working tree like pstack's skills: no understando branch and no patch files.

Removed: the `understando` CLI and its 30 Python scripts (create, discover, build, probe, formalize, maintain, the store and `verify.json` schema, strength, derive, export, coderef, mutation, the formal_* helpers, run_control, testguard, toolprobe, doctor and the rest), `commands/`, `references/adapted/` with the 13 principles, evidence-bars.md, verdicts.md, controls.md, working-rules.md, lean-python.md, tla.md, property.md, `docs/`, the coverage_site hook, `commands.json`, the old fixtures and e2e tests, cosmic-ray, and the Matt Pocock and agent-guards notices (no kept file derives from them). The useful rules now live in `references/`.

Tags: `pre-lean` (21f5264) holds the state just before this cut. `pre-strip` (4658387) holds the review tool from before the strip. Check out either one for anything needed back.
