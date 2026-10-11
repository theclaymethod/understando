"""Conformance: the real ``retry`` replays every terminal behaviour of formal/tla/Retry.tla.

Each vector is one terminal TLC state; its ``hist`` is the outcome of each call the model made.
The real loop gets exactly those outcomes, so a call the model did not make raises IndexError.
"""

import json
import unittest
from pathlib import Path

from mini.retry import retry

VECTORS = Path(__file__).resolve().parents[1] / "formal" / "tla" / "retry_vectors.json"


class RetryTraceReplay(unittest.TestCase):
    def test_every_terminal_behaviour(self) -> None:
        doc = json.loads(VECTORS.read_text())
        max_tries = doc["constants"]["MaxTries"]
        self.assertGreater(len(doc["vectors"]), 3)
        for v in doc["vectors"]:
            self.assertEqual(retry(v["hist"], max_tries), (v["result"], v["tries"]), v)


if __name__ == "__main__":
    unittest.main()
