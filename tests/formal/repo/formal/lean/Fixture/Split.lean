/-! Model of `mini/split.py::split_evenly`, transcribed as written (code-first: model the code,
not the intent). -/
namespace Fixture.Split

def split (total parts : Nat) : List Nat :=
  (List.range parts).map fun i => total / parts + (if i ≤ total % parts then 1 else 0)

/-- The first `(total, parts)` with `0 < parts`, both below `bound`, where the parts do not sum
to the total: the witness search a stuck proof hands to the regression test. -/
def witness (bound : Nat) : Option (Nat × Nat) :=
  (List.range bound).findSome? fun t =>
    (List.range bound).findSome? fun p =>
      if 0 < p ∧ (split t p).sum ≠ t then some (t, p) else none

end Fixture.Split
