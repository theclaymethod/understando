---
name: understando
description: Check whether verifiers capture the user's intent. Interview the owner when designing checks from a feature idea or spec. At review, read the intent implied by existing verifiers back to the owner for correction.
license: MIT
---

# Understando

Choose the starting point from the request. A feature idea or spec calls for a forward pass. A question about what existing tests, evals or properties establish calls for a backward pass. Either pass can stand alone.

## Forward pass

Follow Bootstrap's interview technique. Read the project materials and existing checks first. Start with one ordinary user journey and your best reading of what should happen. When the owner has already settled a rule, use it. Spend the interview on decisions that would change a verifier's verdict.

1. Find two plausible rules that fit what you know. Change one detail in a reachable example until the rules predict different outcomes. Label a hypothetical as such. Check existing guardrails before asking about it.
2. Ask what the user should experience. Offer distinct choices, a reason for your recommendation and room for a custom answer. Group related independent questions in short numbered bullets. Letter the choices so the owner can reply with a number and a letter. Wait before asking a question that depends on the answer. Use the owner's distinction to pick the next example.
3. At the end of each major topic, read back the decisions, assumptions and open questions in short bullets. Ask the owner to confirm or correct your reading. End the turn there. Apply corrections and confirm the revised reading before advancing. Stop probing when another answer would leave the checks unchanged.
4. After the final confirmed readback, show the scenarios and request approval in a separate turn when preparing a suite. Form verifiers from confirmed intent and approved scenarios. Keep deferred decisions open. When the user has already supplied a confirmed spec and asks for an evidence plan, proceed directly on the settled promises.

## Backward pass

Start with the verifiers. Inspect their actual assertions, inputs and recorded runs. Consult the request, prior decisions and corrections for context. Make the first sentence a correctable reading in your own words, such as “I think you wanted a collaborator to open the document directly from the link.” Follow that reading with the assertion that supports it. Say what actually ran, what you inferred and where the checks leave room for a different experience.

When two policies fit the same passing result, describe a concrete case where the user would see the difference. Ask whether your reading matches their intent and wait. For example, opening a newly shared link proves it opens. After an edit, should the same link show the original or the latest version? Keep the interpretation provisional until the owner answers. Preserve any expressly deferred decision.

After a correction, restate the revised intent. Identify which existing verdicts still hold, which verifier needs to change and which claims lack evidence. Use the forward interview if the correction exposes a consequential new choice.

## Choosing evidence

For each confirmed promise, give the starting condition, action and expected observation. Reuse checks that already distinguish acceptable behavior from a plausible mistake. Pick the smallest check for each remaining gap. Use an end-to-end exercise for a user journey, a model-checked property for event orderings or contrasting eval cases for a judgment call. State the assumptions that connect a model to the running product.

Link each check to the decision and any recorded revision, conditions and outcome. Mark unrun checks as proposed. Distinguish a product that violates a confirmed promise from a verifier that rewards the wrong outcome. When asked to verify, run the supported checks and explain what the results establish in user terms.

With CStack available, use Bootstrap's discovery prompts for the forward interview. Use Adversarial Cases to challenge a proposed verifier, Cross-Examine for a disputed verdict and Create Eval for runnable rows. Carry approved scenarios and open decisions into the project's existing ledger.
