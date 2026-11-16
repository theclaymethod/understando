# Can Understando discover the spec with CStack?

Run the [paired owner replay](https://github.com/theclaymethod/cstack/tree/78c042c/evals/spec-discovery) with this repository’s SKILL.md to exercise D1 and D2. D3 uses real file reads and grader executions in a scratch project.

## Composition exercise

Install Understando, Bootstrap, Adversarial Cases, Create Eval and Cross-Examine in a fresh local project. Keep their reference files. Supply only this session and a Python grader:

```text
Owner: Publish a card with its chosen illustration. Reviewers can see the illustration cropped or in full.
QA: I published a card with a fox, opened it immediately, saw the fox. The attached grader passed.
Owner: Leave deletion for later.
```

```python
import sys
print(bool(sys.argv[1].strip()))
```

Ask: “Use Understando to review session.md and the existing grader. Use the installed CStack skills where they help you challenge the proof and discover my spec. Leave your review and the one decision you need from me. Review only.”

Grade the actual tool observations and resulting review. Did it use a relevant primitive? Did it run an incorrect illustration and a valid presentation through the existing grader? Did it distinguish QA’s immediate observation from the scorer’s inability to detect wrong identity? Did it ask a concrete question about a remaining ambiguity, preserve accepted alternatives, and leave deletion open? A suggested owner policy remains provisional. Scored rows or changes to grade.py would exceed the requested review. The explicit invitation to use CStack makes this a composition exercise, not a test of unprompted skill selection.

In a fresh run, Understando read Bootstrap, its discovery prompt card and Adversarial Cases. The unchanged grader returned true for full fox, cropped fox, owl and broken image, and false for whitespace. The review distinguished those text probes from QA’s single visual observation. It asked which image should appear after the source changes without republication, recommended the original provisionally, and left deletion deferred. [Tool observations and resulting review](observations.json)
