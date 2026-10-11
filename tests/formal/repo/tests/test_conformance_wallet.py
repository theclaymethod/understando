"""Conformance: the real ``withdraw`` against its Lean model (formal/lean/Fixture/Wallet.lean).

Two sources of model outputs: the committed vectors that the Lean ``vectors`` executable prints
(edge grid plus pseudo-random inputs), and, with FORMAL_ORACLE set to that executable, random
inputs that the model answers live. FORMAL_REQUIRE_ORACLE=1 makes a missing oracle a failure.
"""

import json
import os
import random
import subprocess
import unittest
from pathlib import Path

from mini.wallet import withdraw

VECTORS = Path(__file__).resolve().parents[1] / "formal" / "lean" / "withdraw_vectors.jsonl"


class WithdrawConformance(unittest.TestCase):
    def test_the_lean_vectors(self) -> None:
        rows = [json.loads(line) for line in VECTORS.read_text().splitlines()]
        self.assertGreater(len(rows), 100)
        for v in rows:
            self.assertEqual(withdraw(v["balance"], v["amount"]), v["out"], v)

    def test_random_inputs_against_the_lean_oracle(self) -> None:
        oracle = os.environ.get("FORMAL_ORACLE")
        if not oracle:
            if os.environ.get("FORMAL_REQUIRE_ORACLE") == "1":
                self.fail("FORMAL_ORACLE is not set")
            self.skipTest("FORMAL_ORACLE is not set")
        rng = random.Random(int(os.environ.get("FORMAL_SEED", "2")))
        pairs = []
        for _ in range(3000):
            b = rng.randint(-10**12, 10**12)
            # Half the amounts land near the balance, where the guard decides.
            a = b + rng.randint(-2, 2) if rng.random() < 0.5 else rng.randint(-10**12, 10**12)
            pairs.append((b, a))
        stdin = "".join(f"{b} {a}\n" for b, a in pairs)
        out = subprocess.run([oracle, "--oracle"], input=stdin, capture_output=True, text=True,
                             check=True).stdout.split()
        self.assertEqual(len(out), len(pairs))
        for (b, a), model in zip(pairs, out):
            self.assertEqual(withdraw(b, a), int(model), (b, a))


if __name__ == "__main__":
    unittest.main()
