<!--
adapted-from: skills/engineering/domain-modeling/GLOSSARY-FORMAT.md
source: mattpocock-skills
source-version: 1.3.1
license: MIT, Copyright (c) 2026 Matt Pocock. See THIRD_PARTY_NOTICES.md.
original-skill: domain-modeling
-->
# GLOSSARY.md format

## Structure

```md
# {Context Name}

{One or two sentences on what this context is and why it exists.}

## Language

**Order**:
{A one or two sentence description of the term}
_Avoid_: Purchase, transaction

**Invoice**:
A request for payment sent to a customer after delivery.
_Avoid_: Bill, payment request
```

## Rules

- Be opinionated. When several words name one concept, pick the best and list the others under `_Avoid_`.
- Keep definitions to one or two sentences. Define what the term is, not what it does.
- Include only terms specific to this project's context. A general programming concept (timeout, error type, utility pattern) does not belong. Ask whether the concept is unique to this context.
- Group terms under subheadings when clusters emerge. A flat list is fine for one cohesive area.

## Single or multiple contexts

- Single context (most repos). One `GLOSSARY.md` at the repo root.
- Multiple contexts. A `GLOSSARY-MAP.md` at the root lists each context, where it lives, and how contexts relate (events emitted and consumed, shared types).
- If `GLOSSARY-MAP.md` exists, read it to find contexts. If only a root `GLOSSARY.md` exists, it is one context. If neither exists, create a root `GLOSSARY.md` when the first term is resolved. With several contexts, infer which one the topic belongs to and ask when unclear.

Done when: every resolved term has a tight definition and its `_Avoid_` words.
