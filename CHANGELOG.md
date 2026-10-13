# Changelog

## The verifier-first gate

The skill now enforces the order that it advised. While it is active, a `PreToolUse` hook (registered in the SKILL.md frontmatter) denies a write to a source file until a verifier has been seen to fail. Run `scripts/gate.sh start "<invariant>"`, write the verifier, then run `gate.sh red -- <command>`. For a behavior that exists already, run `gate.sh red --control <control.sh args> -- <command>`: `control.sh` plants a bug in a throwaway copy and the verifier must fail on it. `gate.sh green` records the pass and notes a verifier that changed after it went red.

The hook allows tests, specs, fixtures, `formal/`, `*.lean`, `*.tla`, `*.cfg`, `*.md` and verify skills at any time, and any file outside the repo. `gate.sh allow GLOB` adds more verifier paths. `gate.sh off "<reason>"` is for when the user says to skip. The state is per repo, in `~/.understando/gate`, and expires after 12 hours. For Bash the hook checks redirects, `tee`, `sed -i`, `perl -i`, `patch` and `git apply`, and it ignores `>` inside quoted text and heredoc bodies. That check is a best effort. Codex has no skill hooks: `modes/build.md` shows the `~/.codex/hooks.json` entry. The hook needs `jq`; `setup.sh --check` reports it.

## The lean cut

understando is now a light, markdown-first skill after the model of pstack's verification skills, with our preferences for what counts as a verifier and which tools to use. SKILL.md is a router to `modes/`, `references/` and thin shell wrappers in `scripts/`. It keeps no store and no state between runs, and it writes into the working tree like pstack's skills: no understando branch and no patch files.

Removed: the `understando` CLI and its 30 Python scripts (create, discover, build, probe, formalize, maintain, the store and `verify.json` schema, strength, derive, export, coderef, mutation, the formal_* helpers, run_control, testguard, toolprobe, doctor and the rest), `commands/`, `references/adapted/` with the 13 principles, evidence-bars.md, verdicts.md, controls.md, working-rules.md, lean-python.md, tla.md, property.md, `docs/`, the coverage_site hook, `commands.json`, the old fixtures and e2e tests, cosmic-ray, and the Matt Pocock and agent-guards notices (no kept file derives from them). The useful rules now live in `references/`.

Tags: `pre-lean` (21f5264) holds the state just before this cut. `pre-strip` (4658387) holds the review tool from before the strip. Check out either one for anything needed back.
