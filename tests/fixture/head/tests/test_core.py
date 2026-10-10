import unittest

from wallet.core import OverdraftError, withdraw


class OverdraftTest(unittest.TestCase):
    """The good verifier: it fails when the overdraft guard goes away."""

    def test_withdraw_refuses_an_overdraft(self) -> None:
        with self.assertRaises(OverdraftError):
            withdraw(10, 11)


class BalanceTest(unittest.TestCase):
    """The verifier that cannot fail: it never looks at the value it gets."""

    def test_withdraw_gives_an_int(self) -> None:
        self.assertIsInstance(withdraw(10, 3), int)


if __name__ == "__main__":
    unittest.main()
