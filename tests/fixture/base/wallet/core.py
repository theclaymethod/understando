"""A small wallet. The base commit of the understando fixture."""


def withdraw(balance: int, amount: int) -> int:
    return balance - amount
