---
name: understando
description: Use when a developer needs to make their intended behavior explicit, reconcile a working spec with evidence and owner judgments, or link a consequential clause to verification.
license: MIT
---

# Understando

The owner carries a spec in their head. Your job is to maintain the best available representation of it and make its consequential promises verifiable.

Start with one user journey. Read the request, relevant examples, owner corrections and the PStack decision log. Find the existing representation, whether it is prose, a statechart, an eval index or an E2E assertion. Write the smallest clause you think the owner means. Attribute it to the source that supports it and distinguish an inference from an owner decision. If a spec is missing, start a working draft. For a read-only review, show the proposed change inline.

Use a recording, trace, email, diff or bootstrapped scenario to test that reading. Identify what happened, under which conditions, and the owner’s judgment of whether it was right or wrong. A run can expose a distinction the draft missed. If several intentions fit, keep the question open and ask the one question whose answer changes the outcome. Label a synthetic example as a scenario. It supplies a choice for the owner to judge.

Revise the affected clause when evidence of intent warrants it. Preserve unrelated promises, the event each bound applies to, and unresolved cases. If a run violates a confirmed clause, keep the clause and identify the deciding procedure. If the verifier rewards the wrong behavior, correct its expectation. Direct the developer’s attention to the remaining ambiguity or mismatch with the largest user consequence.

Solidify a supported clause with a discriminating check. Use PStack’s verification toolkit or the project’s existing check. An E2E replay, an eval, a deterministic assertion or a checked statechart property can express the same promise. Prefer one that rejects the known wrong outcome and accepts a legitimate alternative. In the verification index, link each relevant check to the part of the clause it covers, with its revision, conditions and observed result. If there is no index, start with those links beside the clause. Label proposed checks as proposals. When new owner evidence changes the promise, revisit its linked checks.

Leave the reader with the specific change in understanding, its source, and what verification has established. If the evidence already supports the current representation, retain it and show why.
