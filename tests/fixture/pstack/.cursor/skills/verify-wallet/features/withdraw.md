# Withdraw money

A user withdraws an amount from a balance with the CLI.

## Sub-features

- `withdraw-ok` debits an amount within the balance.

## How to get to it (user POV)

- Run `python3 -m wallet withdraw BALANCE AMOUNT`.

## Driving it with the wallet CLI

Preconditions:

- The doctor passes.

- **Withdraw.** Run `python3 -m wallet withdraw 10 3`. Stdout is `7`. (written by hand: understando keeps this line)

## Gotchas

- Whole numbers only.
