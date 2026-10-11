<!--
adapted-from: skills/unslop/SKILL.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: unslop
-->
# Unslop core

Edit prose to remove AI patterns. Scan for the patterns below, then rewrite. Preserve meaning and match the intended tone. Apply to every prose surface: reply, PR section, explainer, commit body.

## Content

- **Superficial -ing phrases** ("highlighting", "ensuring", "showcasing"). Delete, or expand with real sources.
- **Vague attributions** ("experts believe"). Name the source or delete.

## Language

- **AI vocabulary.** Additionally, crucial, delve, enduring, enhance, fostering, garner, interplay, intricate, landscape (abstract), pivotal, showcase, tapestry (abstract), testament, underscore, vibrant. Use a plain word.
- **Fancy ways to say "is".** "serves as", "stands as", "boasts", "features". Write "is" or "has".
- **"Not just X, but Y."** State the point directly.
- **Rule of three.** Use the natural number of items.
- **Synonym cycling.** Pick one word for one thing and repeat it.
- **False ranges.** "from X to Y" with no real scale. List the topics.

## Style

- **No long dashes.** Use periods or commas. No parentheses, en dashes or hyphen-as-dash.
- **Colons.** Fine before a list or example. Not as a mid-sentence connector.
- **Bold.** Do not bold every proper noun or acronym.
- **Inline-header lists.** A bold label and colon that restates the line is the tell. Write prose. A bold lead-in that ends in a period and is followed by new detail is fine.
- **Headings.** Sentence case.
- **Emojis and curly quotes.** Remove decorative emojis. Use straight quotes.

## Communication artifacts and filler

- **Chatbot phrases** ("I hope this helps", "Certainly!"). Remove.
- **Sycophancy** ("Great question!"). Respond directly.
- **Filler.** "In order to" becomes "To". "Due to the fact that" becomes "Because". Delete "It is important to note that".
- **Hedging.** "could potentially possibly" becomes "may".
- **Generic conclusions.** State specific plans or facts.

## Jargon and plain speech

- **Abstract metaphor nouns** (substrate, wedge, vector, nexus, primitive as noun, surface as in "API surface", scaffolding, paradigm, ratchet, endgame, north star, flywheel). Use the concrete word: "base", "add", "way", "the last phase".
- **Say what it does, not how it feels.** Name the mechanism or a number. If the sentence could sit unchanged in another project's docs, cut it.
- **Split dense sentences.** One idea per sentence.
- **Active voice.** Name the actor. Passive is fine only when the actor is unknown or does not matter.
- **Cut adverbs** or use a stronger verb. "significantly improves" becomes the measured delta.
- **Plain words.** "use" over "utilize" and "leverage", "help" over "facilitate", "if" over "in the event that".
- **Mannered prose.** Replace aphorisms, figurative verbs and personified code with the literal phrase.
- **Over-compression.** Keep articles and verbs. Spell out arrows and abbreviations.

Done when: a final scan finds none of the patterns above.
