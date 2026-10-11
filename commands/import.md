# import

Record outside evidence as a verifier: `understando import <kind> <file> --claim C01 --description "<STE text>"`. The kinds are show-me-your-work (a decision log TSV), lean (a proof file), verify-feature (a verify-<app> feature file), nemesis-review (a spec), evo and impeccable (JSON results). For a Lean file, add `--conformance-source` to name its conformance run.

Each stop of this playbook ends with one question to the user. Ask it as [Asking the user](../references/working-rules.md#asking-the-user) tells you: the situation, a Next line, and numbered options.

- The import reads the format of the file, not a tool version.
- A file with a wrong format is `stale`: it backs no claim, and `doctor` reports it.
- `doctor` reads each imported file again. A file that changed after the import is stale too. Import it again to refresh it.
