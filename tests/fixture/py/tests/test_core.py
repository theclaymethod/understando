import pytest

from wallet.core import withdraw


def test_withdraw_debits_and_refuses_an_overdraft():
    assert withdraw(10, 3) == 7
    with pytest.raises(ValueError):
        withdraw(10, 11)
