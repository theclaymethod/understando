import unittest

from wallet.core import OverdraftError, withdraw


class OverdraftTest(unittest.TestCase):
    """The good check: it fails when the overdraft guard goes away."""

    def test_withdraw_refuses_an_overdraft(self) -> None:
        with self.assertRaises(OverdraftError):
            withdraw(10, 11)


class ExactTest(unittest.TestCase):
    """It reads the value: a debit of 3 from 10 leaves 7."""

    def test_withdraw_debits_the_amount(self) -> None:
        self.assertEqual(withdraw(10, 3), 7)


class BalanceTest(unittest.TestCase):
    """The check that cannot fail: it never looks at the value it gets."""

    def test_withdraw_gives_an_int(self) -> None:
        self.assertIsInstance(withdraw(10, 3), int)


if __name__ == "__main__":
    unittest.main()
