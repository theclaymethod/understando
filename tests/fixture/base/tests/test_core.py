import unittest

from wallet.core import withdraw


class BalanceTest(unittest.TestCase):
    def test_withdraw_gives_an_int(self) -> None:
        self.assertIsInstance(withdraw(10, 3), int)


if __name__ == "__main__":
    unittest.main()
