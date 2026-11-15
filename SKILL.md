---
name: understando
description: Recover a ticket’s intended behavior or reconcile its spec with user decisions, observed behavior, and verification. Use when reviewing the impact of a change or keeping a spec and its checks in sync.
license: MIT
---

# Understando

Start with the consequence a user cares about. For each disputed or changed behavior, answer “Under these conditions, when I do this, what should happen, and how do we know?”

## Recover the rule

Find the ticket, the project's active spec or state chart, and the applicable PStack decision. Follow references to user statements, C Stack Expert Mode corrections, external documents, emails, or timestamped recordings. Identify whose judgment each source represents and its scope. Cite the actual clause, message, or timestamp. If the decision record is unavailable, say which assumption depends on it.

Use an explicit decision within its stated conditions. A correction can rule out an outcome while leaving several acceptable replacements. Preserve which event each quantity governs. One send attempt and at most one inbox delivery are compatible rules. A minimum number of successful deliveries needs its own evidence, even when one exception explicitly permits zero. Treat behavior inferred from code, a video of the app, or a passing check as a candidate until a source establishes intent. With no active spec, draft the smallest ticket-level rule the evidence supports. With an existing spec, compare each relevant clause with the decision and observed behavior. Check applicability and supersession before treating a newer source as authoritative.

Apply an explicit rule across its stated scope even when a proof covers fewer starting states. Record the uncovered case as a verification gap. If the sources leave a consequential choice open, vary one condition from the real ticket. Ask one question only if its answer changes the ticket decision. Vary one observable outcome at a time. For a complaint about duplicate deliveries, a separate decision might concern whether zero deliveries are acceptable. Banner wording or retry policy needs its own source. Keep that scenario provisional and continue with the clauses already settled.

## Link verification to the spec

Use the project's high-level eval index. Give each rule a stable clause reference and link the intent source, applicable decision, and each relevant check by file and assertion, scenario, chart transition, or formal property. A deterministic E2E assertion is an eval in this index. Reuse it directly. An agent walkthrough supplies the steps and observations for a repeatable check. Derive its expected outcome from the spec.

For each link, compare what the check actually observes with the rule's conditions and expected result. Record the revision and scope of the available run evidence. Inspect formal assumptions, chart guards, and E2E setup where they narrow the claim. Use the project's PStack verification workflow for execution. A chart by itself describes the behavior it models. A run or proof supplies evidence about that model or implementation.

## Choose what to double-check

Start with one question: **What could a user experience that violates this clause while every linked check still passes?** Trace a plausible answer through the changed procedure and a real caller, persisted record, or downstream consumer. Use evidence from this change to pick the probes that matter.

| Where a check can drift | What to inspect |
| --- | --- |
| The expected answer changes with the implementation | Follow a snapshot refresh, shared helper, or eval grader back to the approved example. Could both sides repeat the same mistake? |
| A success signal arrives before the promised effect | Observe the recipient, the next session, or the durable value after queued work settles. A successful retry can also hide a duplicate from the first attempt. |
| The setup quietly excludes affected users | Compare the fixture, role, feature flag, or initial model state with the affected population. Trace an existing record or an alternate entry point through the same rule. |
| A property passes without exercising the critical transition | Check whether its trigger is reachable. Compare the model’s atomic step with the implementation’s actual event order and persistence boundary. |
| A result keeps its name after its meaning changes | Compare the spec, assertion, and run revisions. Inspect changed tolerances, skipped cases, and grader inputs before carrying an earlier pass forward. |

Prioritize the clause where a plausible mismatch would do the most harm. Explain who is exposed, what survives rollback, how soon anyone would notice, and which part of the evidence is weak. A single misdirected email can warrant attention before a widely visible layout defect because the recipient already has it. Record why the first recheck takes priority in the ticket or index.

State the assumption on which that risk turns and the observation that would disprove it. Use PStack’s existing check or an authorized direct replay through the affected user's entry point. Where feasible, exercise a known-bad case and see whether the check catches it. Record the actual observation, revision, and residual gap on the same spec entry. If replay is unavailable, give the exact starting state, action, and expected result for the reviewer. Reserve questions for decisions about intent.

## Reconcile and explain the impact

Trace in both directions. From each changed clause, find affected expectations and coverage gaps. From each affected check, identify the clause that justifies its expectation. Surface checks that encode an unsupported assumption.

In a sync task, update the established spec and index in place for resolved decisions, preserving source references and exceptions. With no existing index, use a compact mapping alongside the ticket spec. For each clause show its intent source, decision, actual assertion or property, and result with revision and limits. Keep unrelated clauses in place when a decision changes one exception. In a review, show the proposed clause and its index entry, including any partial or missing coverage. A passing badge assertion, for example, covers the displayed status. A promise about the next playback position needs evidence of that position. Route mismatched behavior to the deciding file and procedure, and stale expectations to the project's verification workflow. Preserve unresolved conflicts for a user decision.

Lead the handoff with what a user will experience. Show one path from the decision through the responsible procedure to the observable result. Link the relevant verification and name the nearest scenario it leaves open. Call out a workaround when the code shows one, including the second place someone would have to change to keep the behavior consistent.
