---- MODULE Retry ----
(* Model of mini/retry.py::retry. Each call's outcome is the environment's choice; hist records
   the outcomes the loop consumed, so a terminal state is one whole behaviour (a test vector). *)
EXTENDS Naturals, Sequences

CONSTANT MaxTries

Outcomes == {"ok", "transient", "fatal"}
Results == {"running", "ok", "fatal", "gave_up"}

VARIABLES tries, result, hist
vars == <<tries, result, hist>>

TypeOK == /\ tries \in 0..MaxTries
          /\ result \in Results
          /\ hist \in Seq(Outcomes)
          /\ Len(hist) = tries

Init == tries = 0 /\ result = "running" /\ hist = <<>>

Call(o) == /\ result = "running"
           /\ tries < MaxTries
           /\ tries' = tries + 1
           /\ hist' = Append(hist, o)
           /\ result' = CASE o = "ok" -> "ok" [] o = "fatal" -> "fatal" [] OTHER -> "running"

GiveUp == /\ result = "running"
          /\ tries = MaxTries
          /\ result' = "gave_up"
          /\ UNCHANGED <<tries, hist>>

\* The loop has returned: an explicit stutter, so TLC's deadlock check stays on.
Done == result # "running" /\ UNCHANGED vars

Next == (\E o \in Outcomes : Call(o)) \/ GiveUp \/ Done

Spec == Init /\ [][Next]_vars /\ WF_vars(Next)

\* Safety: never more than MaxTries calls.
Bounded == tries <= MaxTries
\* Safety: no call after an "ok" or a "fatal".
NoCallAfterStop == \A i \in 1..Len(hist) : hist[i] # "transient" => i = Len(hist)
\* Safety: "ok" only when the last call succeeded; "gave_up" only after MaxTries transient calls.
ResultHonest == /\ result = "ok" => hist[Len(hist)] = "ok"
                /\ result = "gave_up" => tries = MaxTries /\ \A i \in 1..Len(hist) : hist[i] = "transient"
\* Liveness: the loop returns.
Termination == <>(result # "running")
====
