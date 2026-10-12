---- MODULE Counter ----
EXTENDS Naturals
CONSTANT Max
VARIABLE n
Init == n = 0
Inc == n < Max /\ n' = n + 1
Done == n = Max /\ UNCHANGED n
Next == Inc \/ Done
Bounded == n <= Max
====
