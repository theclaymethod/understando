---
name: understando
description: Review a development session or help design a change by expressing the developer's intended behavior as checks.
license: MIT
---

# Understando

The deliverable is a list of checks that together express the spec. In a review, read the session from the original request through the developer's corrections. For a proposed change, start with the intended user journey. Consult the project's decisions, examples and existing verifications. An independent reading by a subagent can help when intent is scattered across a long session. Trace each proposed expectation to its source and distinguish your inference from a developer decision.

Start with an ordinary case. Vary one condition that could change what the user should observe. Look for a nearby failure the check must catch and a legitimate alternative it must allow. If the evidence supports several outcomes, ask the developer about the concrete case that distinguishes them.

When the developer is unsure, recommend an outcome and give your reason. Walk through what someone would experience under that choice and a plausible alternative. Show which check their decision would change, then ask what they prefer. Keep an undecided expectation open and continue with the settled checks.

For each check, state the starting conditions, the action and the observable outcome. Choose a verification that can observe the event the promise concerns. A replay, an eval, an assertion or a statechart property may fit. Narrow overlapping checks while preserving distinct boundaries.

Compare the list with the verifications actually created. Link each existing check to the promise it covers and record the revision, conditions and observed result when available. Use the project's verification index or put the links beside the clause. If a run violates a confirmed promise, retain the promise and report the failure. If a verifier rewards the wrong behavior, identify the expectation to change. Revisit affected checks when the developer revises the spec.

A session review ends with the check list, its coverage and any open decisions. Label missing checks as proposed. When asked to verify the change, also create and run the needed checks where the project supports them and report what happened.
