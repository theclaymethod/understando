"""A small wallet. The head commit of the understando fixture: the PR under review."""


class OverdraftError(ValueError):
    pass


def withdraw(balance: int, amount: int) -> int:
    """
    @cc [owner:fixture,label:product] no-overdraft
    `withdraw` refuses an amount above the balance with `OverdraftError`.
    """
    if amount > balance:
        raise OverdraftError(f"{amount} is above the balance")
    return balance - amount
