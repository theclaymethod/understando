def withdraw (balance amount : Int) : Int :=
  if amount > balance then balance else balance - amount

theorem withdraw_nonneg (b a : Int) (h : 0 ≤ b) : 0 ≤ withdraw b a := by
  unfold withdraw; split <;> omega
