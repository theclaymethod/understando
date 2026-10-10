# Refuse overdrafts in the wallet

- `withdraw` refuses an amount above the balance. `OverdraftTest` covers it.
- `withdraw` returns the balance minus the amount. `BalanceTest` covers it.
- The wallet module is safe to call from many threads.
- A denial message names no account number. A gpt reviewer read each message in a fresh context.
