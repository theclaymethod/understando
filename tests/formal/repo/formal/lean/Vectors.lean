import Fixture.Wallet
open Fixture.Wallet

/-! Conformance vectors for `withdraw`: a grid of edge inputs plus pseudo-random ones, each with
the model's output, as JSON lines. With `--oracle`, read `balance amount` pairs from stdin and
print the model's output for each: the Python property test's live oracle. -/

def lcg (s : Nat) : Nat := (s * 6364136223846793005 + 1442695040888963407) % 18446744073709551616

def toInt (s : Nat) (span : Nat) : Int := (Int.ofNat (s / 65536 % (2 * span + 1))) - Int.ofNat span

def line (b a : Int) : String :=
  s!"\{\"balance\": {b}, \"amount\": {a}, \"out\": {withdraw b a}}"

partial def oracle (stdin : IO.FS.Stream) : IO Unit := do
  let l ← stdin.getLine
  if l.isEmpty then return
  match (l.trimAscii.toString.splitOn " ").filterMap String.toInt? with
  | [b, a] => IO.println (toString (withdraw b a))
  | _ => IO.println "error"
  (← IO.getStdout).flush
  oracle stdin

def main (args : List String) : IO Unit := do
  if args == ["--oracle"] then
    oracle (← IO.getStdin)
    return
  for b in [-3, -1, 0, 1, 2, 10, 1000000000000] do
    for a in [-2, -1, 0, 1, 2, 9, 10, 11, 1000000000000, 1000000000001] do
      IO.println (line b a)
  let mut s := 42
  for _ in [0:500] do
    s := lcg s
    let b := toInt s 1000
    s := lcg s
    let a := toInt s 1000
    IO.println (line b a)
