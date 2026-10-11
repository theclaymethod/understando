<!--
adapted-from: skills/poteto-mode/playbooks/feature.md
source: pstack
source-version: 0.15.5
license: MIT, Copyright (c) 2026 Lauren Tan. See THIRD_PARTY_NOTICES.md.
original-skill: poteto-mode
-->
# Feature playbook

Use for `understando build`. You own the design: plan, review, verify. Delegate implementation and stay in the lead.

1. **Map the affected area.** Read the subsystem the change touches and write what you learned in a few lines. Done when: a reader could name the files and the data flowing through them.
2. **Explore designs when the shape is open.** Compare two or three candidate designs for any code that crosses a function boundary. Done when: one design is chosen and the rejected ones are named with a reason.
3. **Write the throughput checkpoint as four items.** A dimension that does not apply keeps its item as `n/a: <reason>`.
   - Blocking first steps. Gates that run before any fan-out.
   - Independent workstreams. Disjoint files, services or layers parallelize. Shared writes serialize.
   - Shared mutable state. Split the target by default. Serialize only for a real invariant.
   - Smallest safe decomposition. If one worker is best, say why.
4. **Delegate the code to a subagent** with a specific scope: file paths, the named data shape with its organizing structure (a state machine over booleans, a table over branching, a typed model over repeated shape assumptions, per model-the-domain), chosen before the delegate writes logic, and success criteria. Commit small and often. Done when: you reviewed the diff yourself.
5. **Verify on the matching surface.** An inconclusive result or a wrong surface is not a pass. Flag it. Done when: the verifier that went red before the code now passes on the real surface.
6. **Rebase into small, ordered commits** and stack follow-ups, using sequence-verifiable-units. Build, verify and commit each unit before the next.
7. **If the design is contested, get a second opinion** from a different model family before shipping (see subagents.md).

Code-coupled work (one feature, one migration) goes to a single owner with the checkpoint inline. The owner fans out internally after the blocking phase. Fan out at the parent level only for slices that produce independent artifacts. Rewrite the checkpoint at phase boundaries. Start a fresh owner rather than chaining interrupts.

Report: what you built, what you chose and why, the throughput checkpoint, open decisions. Use a table for design alternatives.
