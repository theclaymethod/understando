---
name: understando
description: Review a development session or help design a change by expressing the developer's intended behavior as checks.
license: MIT
---

# Understando

The deliverable is a list of checks that together express the spec. In a review, read the session from the original request through the developer's corrections. For a proposed change, start with the intended user journey. Consult the project's decisions, examples and existing verifications. An independent reading by a subagent can help when intent is scattered across a long session. Trace each proposed expectation to its source and distinguish your inference from a developer decision.

Before raising a hypothetical, trace it through the supported product path and inspect existing guardrails and checks. If the guard already prevents that outcome or a check already distinguishes it, move on without creating a test or asking the owner. Look for a reachable variation with a genuinely new consequence.

When green checks fit different readings of the session, ask yourself: “Which two rules both explain every observation? Where would a user see their first difference? Which existing check could pass under either rule?” Check the session for an answer first. Change one fact, describe the competing outcomes, and ask the developer one question whose answer would change a consequential check. Carry the answer back to the affected checks. Stop when more questions would leave the checks unchanged or revisit a deferred decision.

When CStack is available, use Bootstrap’s discovery prompts for the interview and Adversarial Cases to try to break a proposed check while preserving a legitimate alternative. Use Cross-Examine for a disputed score and Create Eval when the developer wants runnable rows. Reuse the project’s situations and decision ledger when present. A challenge exposes a possible gap. Only evidence of intent or an owner decision settles the expectation.

When the developer is unsure, recommend an outcome and give your reason. Walk through what someone would experience under that choice and a plausible alternative. Show which check their decision would change, then ask what they prefer. Keep an undecided expectation open and continue with the settled checks.

For each check, state the starting conditions, the action and the observable outcome. Choose a verification that can observe the event the promise concerns. A replay, an eval, an assertion or a statechart property may fit. Narrow overlapping checks while preserving distinct boundaries.

Compare the list with the verifications actually created. Before signing off, match each required condition to something the run actually recorded. Credit the part observed and name any missing condition. Link each existing check to the promise it covers and record the revision, conditions and observed result when available. Use the project's verification index or put the links beside the clause. If a run violates a confirmed promise, retain the promise and report the failure. If a verifier rewards the wrong behavior, identify the expectation to change. When the developer corrects a promise, revise the checks it affects. Reassess any earlier pass against the new expectation. Carry forward unrelated decisions and keep undecided cases open.

A session review ends with the check list, its coverage and any open decisions. Label missing checks as proposed. When asked to verify the change, also create and run the needed checks where the project supports them and report what happened.
