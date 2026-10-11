import Fixture.Split
open Fixture.Split

def main : IO Unit := do
  match witness 12 with
  | some (t, p) =>
    IO.println s!"\{\"function\": \"mini.split.split_evenly\", \"args\": \{\"total\": {t}, \"parts\": {p}}, \"model_output\": {(split t p)}}"
  | none => IO.println "null"
