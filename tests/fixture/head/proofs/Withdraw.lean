-- The model of `withdraw` in wallet/core.py. The fixture records the proof run; no test runs Lean.
def withdraw (b a : Nat) : Option Int := if a > b then none else some ((b : Int) - a)

theorem withdraw_nonneg (b a : Nat) (r : Int) (h : withdraw b a = some r) : 0 ≤ r := by
  unfold withdraw at h
  split at h <;> simp_all
  omega
