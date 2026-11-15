# Understando release review

On 2026-11-15 we ran C Stack Cross-Examine against the skill with SHA-256 `05fdabb31fc10b2409f876537e74d673e42279b9c42127c3da2b6d557169ef45` on upstream commit `109a9b5`. The release question was whether the skill reconciles verification with the user's intended outcome and preserves the scope of that decision.

These are synthetic development scenarios. Each review used the frozen skill and the ticket evidence supplied in its prompt. The adversarial evaluator challenged the archive verdict, a second agent exercised legitimate and incomplete cases, the release coordinator handled repairs, and a fresh intent reviewer assessed the contract and results. The review used isolated scratch paths on a shared host. It makes no access-isolation or held-out performance claim.

| Input | Observed review | Independent judgment |
| --- | --- | --- |
| Owner wants archived folders hidden by default. Green screenshot shows a trash icon. Model fixture contains zero archived folders. | Held visibility unverified and proposed opening the list with one archived and one active folder. | Accepted. A visibility pass based on the two green signals would give credit for a different observable and an unexercised trigger. |
| Owner, decision and spec require local export bytes to survive restart. Current-revision E2E reads the same exported bytes after restart. | Accepted the existing check across the stated local-export scope. | Accepted. This is the legitimate-pass control. |
| Owner rejects two invitations from one click. Older mock observes one enqueue. Current recording traces one click to two deliveries after retry. No spec exists. | Recovered an upper bound, identified the violation, and left zero deliveries and the implementation cause open. | Accepted within the recorded causal scope. |

The repository check on upstream main rejected the new skill solely because its frontmatter lacked the previous verifier-first description verbatim. We reproduced this false rejection and replaced the obsolete copy assertion with discovery-field checks and a real fresh/repeated project install. The install must produce the shipped skill and leave hook settings absent. The independent reviewer accepted the repair. The skill validator and the repository check passed. The repository check skipped its optional mutation, Lean and TLC fixtures because their toolchains were unavailable.

## In-place sync and repair

A fourth case began with a once-per-click send clause, a blue badge clause, and an unrelated draft-saving clause with existing index links. Owner E4 prohibited duplicate delivered invitations and allowed zero deliveries on suppressed addresses. Decision D4 confirmed suppression. E5 changed the badge to gold. At r8 the supplied inbox trace attributed two deliveries to one click while T1 observed one enqueue. R2 showed blue and T2 expected blue.

The first sync preserved the draft rule and found both discrepancies but required exactly one successful delivery to every unsuppressed address. The independent reviewer held that result. The original default governs sending, and the new decision supplies a delivery ceiling. Neither establishes a delivery minimum across failures. We amended the skill to preserve the event each quantity governs and to record why the leading recheck takes priority.

We froze the repaired skill at SHA-256 `8bd6ae289c8cdfa8fffca5f22f9cf95c66e274ec2f75f8ecfb7f9343a0db16ba` and replayed from the original inputs in a separate scratch directory. The resulting spec retained one send attempt, capped deliveries at one, allowed suppressed zeroes, and left the other lower bound open. The index preserved S3/T3, linked both r8 discrepancies, and put duplicate delivery first because copies survive rollback. The three earlier controls retained their verdicts. We inspected the resulting spec and index. No application or mail delivery was exercised. Verification of downstream behavior in these scenarios used only the evidence supplied to each agent.

The independent intent reviewer accepted the repaired revision for this bounded development suite after inspecting the resulting files. The repaired instructions include the invitation example, so its replay establishes regression coverage.
