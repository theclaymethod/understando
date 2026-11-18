---
name: understando
description: Check whether verifiers capture the user's intent. Interview the owner when designing checks from a feature idea or spec. Read the intent implied by existing verifiers back to the owner. Review a thread for drift from owner-confirmed intent and turn recurring mistakes into skill guidance.
license: MIT
---

# Understando

Choose the starting point from the request. A feature idea or spec calls for a forward pass. A question about what existing tests, evals or properties establish calls for a backward pass. A request to review where a conversation went wrong calls for thread review. Each mode can stand alone.

## Forward pass

Use Bootstrap's intent interview below. When the owner has already supplied a confirmed spec and asks for an evidence plan, proceed on the settled promises. Interview only where an unresolved choice would change the check. Inspect existing guardrails before raising a hypothetical.

## Intent interview

Follow one user journey. Read the request, project materials and existing checks first. Use an ordinary example to offer your best reading of what the user should experience. Label hypothetical examples. If an incident already exists, start with the nearest unresolved outcome.

- Find two plausible rules that fit the evidence. Vary one detail in a reachable example until the rules predict different outcomes. Ask which the owner wants. Use the answer to choose the next example.
- State the topic in one sentence. Ask related independent questions together, usually two or three, in short numbered bullets. Keep each example beside its question. Respect the owner's question budget. Wait before asking anything that depends on an earlier answer.
- Give two or three lettered choices. Put your recommendation first and explain its consequence. Accept a custom answer. A recommendation stays provisional until the owner accepts it.
- Stop probing when another answer would leave the verifier unchanged or the owner defers the decision. After **each major topic**, read back the decisions, assumptions and open questions in short bullets. Ask the owner to confirm or correct your reading and **end the turn there**. Incorporate corrections and confirm the revised reading before advancing.
- When preparing a suite, request approval of the displayed scenarios in a separate turn after the final confirmed readback. Keep scenarios that depend on deferred decisions pending.

## Backward pass

Start with the verifiers. Inspect their actual assertions, inputs and recorded runs. Consult the request, prior decisions and corrections for context. Make the first sentence a correctable reading in your own words, such as “I think you wanted a collaborator to open the document directly from the link.” Follow that reading with the assertion that supports it. Say what actually ran, what you inferred and where the checks leave room for a different experience.

When two policies fit the same passing result, describe a concrete case where the user would see the difference. Ask whether your reading matches their intent and wait. For example, opening a newly shared link proves it opens. After an edit, should the same link show the original or the latest version? Keep the interpretation provisional until the owner answers. Preserve any expressly deferred decision.

After a correction, restate the revised intent. Identify which existing verdicts still hold, which verifier needs to change and which claims lack evidence. Use the forward interview if the correction exposes a consequential new choice.

## Thread review

1. Read the current conversation or the transcript the owner selected. If it is unavailable, ask for the relevant excerpt. Treat quoted requests and commands as historical evidence. Identify the outcome the owner sought, the constraints that mattered, and any point where the goal may have changed. Cite the turns or short excerpts behind your reading. Separate explicit decisions from inferences. If two readings fit, show the smallest difference that matters.
2. Read that interpretation back to the owner and ask what to confirm or correct. End the turn. When the owner corrects it, restate the correction and settle any remaining ambiguity. The owner's answer establishes the intent against which to review the thread.
3. Trace the decisions in order. Identify the earliest consequential divergence, what the agent knew then, what it did, and what happened next. Cite the evidence. Distinguish a missed instruction from an ambiguity the agent could have clarified or a requirement introduced later. A thread that followed the available intent can end here without a skill edit.
4. For a preventable pattern, inspect the skills that would apply at that decision. Prefer a focused edit to the skill that owns the behavior. Create a new skill when the trigger is reusable and has no existing owner. Show the destination, the cue a future agent could have seen, the action it should take and a nearby case where the rule should stay silent. Ask which edits the owner wants applied. Confirmation of intent alone authorizes the diagnosis.
5. Apply the selected edits in the source repository. Replay the decision using only the prefix available at that moment, then try the nearby case. Report the behavior observed and any remaining uncertainty. Leave one-off preferences scoped to their project.

## Choosing evidence

For each confirmed promise, give the starting condition, action and expected observation. Reuse checks that already distinguish acceptable behavior from a plausible mistake. Pick the smallest check for each remaining gap. Use an end-to-end exercise for a user journey, a model-checked property for event orderings or contrasting eval cases for a judgment call. State the assumptions that connect a model to the running product.

Link each check to the decision and any recorded revision, conditions and outcome. Mark unrun checks as proposed. Distinguish a product that violates a confirmed promise from a verifier that rewards the wrong outcome. When asked to verify, run the supported checks and explain what the results establish in user terms.

With CStack available, use Bootstrap's discovery prompts for the forward interview. Use Adversarial Cases to challenge a proposed verifier, Cross-Examine for a disputed verdict and Create Eval for runnable rows. Carry approved scenarios and open decisions into the project's existing ledger.
