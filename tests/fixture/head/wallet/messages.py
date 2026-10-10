"""Denial text that a person reads. A model reviewer checked it. No test runs it."""


def denial(account: str, amount: int) -> str:
    return f"We cannot pay out {amount}. The balance is too low."
