"""The wallet CLI: `python3 -m wallet withdraw BALANCE AMOUNT` prints the new balance."""

import sys

from wallet.core import OverdraftError, withdraw


def main(argv: list[str]) -> int:
    if argv[:1] == ["--version"]:
        print("wallet 1.0")
        return 0
    if len(argv) != 3 or argv[0] != "withdraw":
        print("usage: python3 -m wallet withdraw BALANCE AMOUNT", file=sys.stderr)
        return 2
    balance, amount = int(argv[1]), int(argv[2])
    if amount > balance:  # a second guard: the CLI refuses before the wallet sees the amount
        print("refused: the amount is above the balance", file=sys.stderr)
        return 3
    try:
        print(withdraw(balance, amount))
    except OverdraftError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3
    return 0
