# Refuse overdrafts in the wallet

- `withdraw` refuses an amount above the balance. `OverdraftTest` covers it.
- `withdraw` returns the balance minus the amount. `BalanceTest` covers it.
- The wallet module is safe to call from many threads.
- A denial message names no account number. A gpt reviewer read each message in a fresh context.
- No wallet module imports a network library.
- A denial message names the amount. `DenialTest` covers it.
- `withdraw` never returns a negative balance. A Lean proof covers it, with a conformance run against the code.
