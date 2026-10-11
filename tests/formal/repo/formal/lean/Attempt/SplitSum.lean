import Fixture.Split
/-! The proof attempt for the claim "the parts sum to the total", bounded so `decide` can try it.
It does not build on the code as written: the first hard blocker. -/
open Fixture.Split

theorem split_sum_small : ∀ t, t < 6 → ∀ p, p < 6 → 0 < p → (split t p).sum = t := by
  decide
