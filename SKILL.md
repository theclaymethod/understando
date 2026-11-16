---
name: understando
description: At code review, infer the intended user experience from the verifications and invite correction. From a spec, design checks that establish its promises.
license: MIT
---

# Understando

**Backward pass — review.** Read the assertions and recorded outcomes, then the request, decisions and corrections. Open your reply with your own plain-language account of what you think the developer wanted someone to experience. Make it concrete enough for the developer to disagree. Say which part you inferred and what the run actually showed. Invite correction before treating a consequential inference as settled. An independent reading can help when intent is scattered across a long session.

**Forward pass — design.** Start with the developer’s spec or their correction to your restatement. For each promise, identify a situation where a wrong implementation would produce a different observable outcome. Reuse evidence that already distinguishes the two. Choose the smallest remaining check that can tell them apart: an end-to-end exercise for a user journey, a model-checked property for event orderings, or an eval with contrasting examples for a judgment call. Explain what each result could establish, including assumptions needed to connect a model to the running product.

Before raising a hypothetical, trace it through the supported product path and inspect existing guardrails and checks. If the guard already prevents that outcome or a check already distinguishes it, move on without creating a test or asking the owner. Look for a reachable variation with a genuinely new consequence.

When green checks fit different readings of the session, ask yourself: “Which two rules both explain every observation? Where would a user see their first difference? Which existing check could pass under either rule?” Check the session for an answer first. Change one fact, describe the competing outcomes, and ask the developer one question whose answer would change a consequential check. Carry the answer back to the affected checks. Stop when more questions would leave the checks unchanged or revisit a deferred decision.

When CStack is available, use Bootstrap’s discovery prompts for the interview and Adversarial Cases to try to break a proposed check while preserving a legitimate alternative. Use Cross-Examine for a disputed score and Create Eval when the developer wants runnable rows. Reuse the project’s situations and decision ledger when present. A challenge exposes a possible gap. Only evidence of intent or an owner decision settles the expectation.

When the developer is unsure, recommend an outcome and give your reason. Walk through what someone would experience under that choice and a plausible alternative. Show which check their decision would change, then ask what they prefer. Keep an undecided expectation open and continue with the settled checks.

For each retained check, give the starting conditions, action and expected observation. Link the verification and its recorded revision, conditions and outcome when available. Mark missing evidence as proposed. If the run violates a confirmed promise, report the conflict. If the verifier rewards the wrong outcome, identify the expectation to revise.

When corrected, restate the revised experience. Trace the change through the affected expectations, checks and earlier verdicts. Preserve unrelated evidence and deferred decisions. When asked to verify, create and run the needed checks where supported, then read the results back in user terms so the developer can judge the updated interpretation.
