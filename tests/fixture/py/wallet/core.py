def withdraw(balance: int, amount: int) -> int:
    if amount > balance:
        raise ValueError("overdraft")
    return balance - amount
