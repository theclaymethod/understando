# PR 489: each claim, in plain words

Each claim has two parts. **What it is** tells you the rule. **How it is proven** tells you the check, and what happened when we broke the code on purpose (the control).

A control that makes the check fail ("red") shows that the check can find a bug. A control that does not make the check fail ("green") shows that the check is blind to that bug.

## Words to know

- **Finding:** a problem that a check or a judge reports in a draft.
- **Editor:** the model that changes the draft to repair findings.
- **Kind:** the type of document. The four kinds are note, UAP, FMM and 4H.
- **Adapter:** the code for one kind.
- **Core:** the shared loop that all kinds use.
- **Type pin:** a line of bad code that we keep in a test file on purpose. The type checker must reject it. If the checker accepts it, the run fails.
- **Boundary check:** a script that reads the import lines of each file. It fails when a file imports a file that it must not use.

## Proven (25 claims)

For each claim here, a tool check exists, and the check went red on a planted bug.

### Type rules

**C01. Only a gated finding goes to the editor.**
- **What it is:** The editor accepts only an `EditableFinding`. An `EditableFinding` is a finding that passed the editability gate. A raw finding is a type error.
- **How it is proven:** Two type pins (V01, V02) and the full type check (V35). We loosened the types, and the checks went red.
- **Warning:** One control (K01b) made the editor accept any input. Pin V01 stayed green. Only the full type check (V35) found it. Thus, pin V01 is weaker than it looks.

**C02. The wiring cannot mix kinds.**
- **What it is:** The wiring joins an adapter to its settings. A UAP adapter with FMM settings is a type error.
- **How it is proven:** Two type pins (V03, V04). We loosened the types, and both went red.

**C03. The run functions cannot mix kinds.**
- **What it is:** `run_adapter` and `_run_kind` refuse an adapter, a subset or a setup of a different kind.
- **How it is proven:** Two type pins (V05, V06). We loosened the types, and both went red.

**C04. The output writer refuses the note kind.**
- **What it is:** `write_outputs` does not write notes. Thus, the type of its input does not permit the note kind.
- **How it is proven:** One type pin (V07). We loosened the type, and it went red.

### Import rules

**C05. Each docgen file imports only its approved docgen files.**
- **What it is:** A table lists, for each docgen file, the docgen files that it can import. Other imports are not permitted.
- **How it is proven:** The boundary check (V08). We deleted one row from the table, and the check went red.

**C06. No adapter imports another adapter.**
- **What it is:** The code for one kind does not use the code for a different kind.
- **How it is proven:** The boundary check (V09). We added a bad import, and the check went red.

**C07. The core does not know about any kind.**
- **What it is:** The shared loop does not import the CLI or the FMM, 4H, refine or UAP code.
- **How it is proven:** The boundary check (V10). We added a bad import, and the check went red.

**C08. Only the note adapter uses the note writer.**
- **What it is:** Only `clinician_note` (and files on the approved list) can import `cr.note.author` and `cr.note.loop`.
- **How it is proven:** The boundary check (V11). We deleted one row from the approved list, and the check went red.

**C09. Only two files make a finished CR.**
- **What it is:** Only `finished_cr.py` and the test fixture can make a `FinishedCR`. Thus, no code can skip the CR acceptance checks.
- **How it is proven:** The boundary check (V12). We deleted one row from the approved list, and the check went red.

**C10. Only the gate makes an editable finding.**
- **What it is:** Only `findings.py` can make an `EditableFinding`. Thus, no code can skip the editability gate.
- **How it is proven:** The boundary check (V13). We added a bad call in a different file, and the check went red.

### Anti-gaming rules

These rules stop the editor from "repairing" a finding in a way that hides the problem but does not repair it.

**C11. The editor never gets a finding on the do-not-edit list.**
- **What it is:** Some findings must not be repaired by editing text, for example a finding about a lab result. The judge grades them, but the editor does not see them.
- **How it is proven:** An integration test (V14) runs the UAP adapter with a test judge. We deleted the guard line, and the test went red.

**C12. A finding about a fact is editable only where that fact is.**
- **What it is:** An `evidence_bound` finding is about one input fact. The editor can change only a card whose evidence holds that fact.
- **How it is proven:** An integration test (V15). We deleted the guard line, and the test went red.

**C13. A major finding must occur two times before the editor sees it.**
- **What it is:** The judge runs two times. If the second run does not report the same major finding, the editor does not get it.
- **How it is proven:** An integration test (V16). We deleted the guard line, and the test went red.

**C14. The second report must be about the same claim.**
- **What it is:** The second report counts only when it has the same cartridge, the same key and the same place. A report about a different file does not count.
- **How it is proven:** Two integration tests (V17, V18). We deleted the code that compares the claims, and both tests went red.

### Loop rules

**C15. The loop stops when a round does nothing.**
- **What it is:** If the accept rule refuses a round, and that round changed no file, the edit rounds stop.
- **How it is proven:** An integration test (V19) runs the loop with a test adapter and a scripted editor. We deleted the guard line, and the test went red.

**C16. The loop stops when the editor cannot repair a safety finding.**
- **What it is:** A safety-floor finding can be in a file that the editor cannot write. Then the edit rounds stop.
- **How it is proven:** An integration test (V20). We deleted the guard line, and the test went red.

**C17. A broken editor call is never released.**
- **What it is:** If an editor call stops before it is complete, its partial edit is not checked again and is not released.
- **How it is proven:** An integration test (V21). We deleted the guard line, and the test went red.

**C18. The editor cannot finish while a blocking finding remains.**
- **What it is:** The finish tool refuses while a code check reports a blocking finding. It refuses a maximum of three times.
- **How it is proven:** An integration test (V22). We reversed the condition, and the test went red.

**C19. The editor cannot delete a file.**
- **What it is:** The editor can change a file that it can write, but it cannot delete that file.
- **How it is proven:** An integration test (V23) sends a delete command. We deleted the guard line, and the test went red.

**C20. The fallback is the last clean draft, not the first.**
- **What it is:** If the loop must go back, `LastClean` restores the latest kept draft that has no blocking finding.
- **How it is proven:** An integration test (V24). We reversed the condition, and the test went red.

**C21. The judge worker must use test data only.**
- **What it is:** The judiciary reflector refuses a worker that does not tell it "synthetic data only".
- **How it is proven:** An integration test (V25) starts a test worker with 30 bad start messages. We deleted the guard line, and the test went red.

### Same-output rules

**C22. The model requests are the same as the saved copy.**
- **What it is:** `cr docgen` sends requests to the model that are the same, byte for byte, as a saved file (the golden file).
- **How it is proven:** A golden test (V26) compares a hash of each request with the golden file. We changed one byte in the golden file, and the test went red.

**C23. The new note path sends the same requests as the old note path.**
- **What it is:** In 14 scripted sessions, `cr docgen --kind note` sends the same requests as `write_clinician_note`.
- **How it is proven:** A parity test (V27) runs each session through both paths. We deleted the code that the test covers, and the test went red.

**C24. The old UAP and FMM commands use the new path.**
- **What it is:** `cr uap` and `cr fmm` call `cr docgen` with no reflection.
- **How it is proven:** A parity test (V28) compares the requests of the old and new commands. We reversed the condition, and the test went red.

**C25. Each kind refuses a CR that fails the CR-33 check.**
- **What it is:** CR-33 is the acceptance check for a CR. If a CR fails it, no kind makes a document from it.
- **How it is proven:** An integration test (V29) runs each kind on a bad CR. We deleted the guard line, and the test went red.

## Backed (5 claims)

For each claim here, evidence exists, but we did not run it again. It is a record of a past run.

**C26. The new note agent makes fewer failures than production.**
- **What it is:** Two blind labellers agree on failures. The rate goes down from 2.65 to 0.02 for each note.
- **How it is proven:** A pre-registered eval (V30) on 23 test members. gpt-6.1-sol and Opus labelled each note, and they did not know which path made it. This is a record. We did not run it again.

**C27. The new path is not worse than main for FMM, 4H and UAP.**
- **What it is:** After the anti-gaming changes, each kind is at least as good as main.
- **How it is proven:** Frozen judges graded both paths three times on 5 members (V31). Two blind labellers also labelled each document. This is a record.
- **Warning:** The UAP result uses the same 5 members that we used to tune the anti-gaming changes.

**C28. An Opus audit found no gaming in the kept edits.**
- **What it is:** No kept edit hides a problem without a repair.
- **How it is proven:** Opus read each kept edit (V32). This is a model opinion, not a tool check.
- **Warning:** Opus is in the same model family as the author. Thus, it is not a fully independent check.

**C29. Each document costs more.**
- **What it is:** UAP goes up from $0.75 to $1.30. FMM goes up from $0.34 to $0.38. 4H goes up from $0.24 to $0.32.
- **How it is proven:** The cost meter of each run (V33). This is a record.

**C30. All tests and checks pass.**
- **What it is:** 4,249 CR tests, 1,272 harness tests and 74 root tests pass. Ruff, basedpyright and the boundary checks are clean.
- **How it is proven:** The CI jobs ran at the PR head (V34). This is a record. We did not run them again.

## Asserted (5 claims)

For each claim here, only the PR text says it. No check proves it.

**C31. Production does not change.**
- **What it is:** The production service does not import `cr.docgen`. Thus, the new code cannot change production.
- **How it is proven:** It is not proven. A boundary rule that stops `cr_service` from importing `cr.docgen` would prove it.

**C32. The source code is 47 lines smaller than main.**
- **What it is:** The PR deletes more source lines than it adds.
- **How it is proven:** It is not proven. A line count of the diff would prove it.

**C33. A UAP trace label is a label error, not a safety gap.**
- **What it is:** The harness released one UAP plan with a label that needs clinician review. The PR says that the label is wrong, and that the safety floor did not fail.
- **How it is proven:** It is not proven. A clinician must examine it.

**C34. Nobody measured two folded defaults in production.**
- **What it is:** The PR includes two default settings from PRs 438 and 424. Nobody measured them in production.
- **How it is proven:** It is not proven. This is a statement that something is missing.

**C38. The real judge worker operates with `cr docgen`.**
- **What it is:** `cr docgen --reflection judiciary` operates with the real judiciary worker, not only a test worker.
- **How it is proven:** It is not proven. A test (V36) exists, but it skips when judiciary is not built. We planted a bug, and the test skipped and stayed green. Thus, the test cannot fail now.

## Gap (3 claims)

For each claim here, no check exists, and the PR does not state the claim. You must decide if it is important.

**C35. Packet and ledger must be for the same member.**
- **What it is:** `require_same_scope` refuses a packet and a ledger that are for different members or different snapshots.
- **How it is proven:** It is not proven. No test gives it a mismatched pair.

**C36. Nothing uses the deleted `sheet_names`.**
- **What it is:** The PR deletes `sheet_names` from `guidance/_xlsx.py`. The PR assumes that no code calls it.
- **How it is proven:** It is not proven. A search of the repo, or the type check, would prove it.

**C37. In diagnose mode, the error names the bad tool calls.**
- **What it is:** When the model makes tool calls that we do not expect, `submission_text` names those calls. It does not show an empty body.
- **How it is proven:** It is not proven. No test sends unexpected tool calls in diagnose mode.
