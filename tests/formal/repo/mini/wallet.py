"""A pure rule: a withdrawal that never overdraws."""


def withdraw(balance: int, amount: int) -> int:
    """The new balance. A non-positive amount or an amount above the balance is refused."""
    if amount <= 0 or amount > balance:
        return balance
    return balance - amount
