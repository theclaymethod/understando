import unittest

from wallet.messages import denial


class DenialTest(unittest.TestCase):
    """A unit test that no e2e test repeats: it reads the amount in the denial text."""

    def test_denial_names_the_amount(self) -> None:
        self.assertIn("250", denial("ACC-1", 250))


if __name__ == "__main__":
    unittest.main()
