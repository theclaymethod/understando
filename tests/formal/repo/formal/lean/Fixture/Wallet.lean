/-! Model of `mini/wallet.py::withdraw`. Python `int` is unbounded, so the model uses `Int`. -/
namespace Fixture.Wallet

def withdraw (balance amount : Int) : Int :=
  if amount ≤ 0 ∨ amount > balance then balance else balance - amount

/-- A withdrawal never makes a non-negative balance negative. -/
theorem withdraw_nonneg (balance amount : Int) (h : 0 ≤ balance) :
    0 ≤ withdraw balance amount := by
  unfold withdraw; split <;> omega

/-- A withdrawal never raises the balance. -/
theorem withdraw_le (balance amount : Int) : withdraw balance amount ≤ balance := by
  unfold withdraw; split <;> omega

/-- The result is the exact debit or the unchanged balance, nothing else. -/
theorem withdraw_exact (balance amount : Int) :
    withdraw balance amount = balance - amount ∨ withdraw balance amount = balance := by
  unfold withdraw; split <;> simp

end Fixture.Wallet
