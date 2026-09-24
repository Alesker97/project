from inspect import isabstract
import pytest

from src.accounts.account_base import AbstractAccount


def test_abstract_account_is_abstract() -> None:
    assert isabstract(AbstractAccount)


def test_abstract_account_declares_required_methods() -> None:
    assert AbstractAccount.__abstractmethods__ == {
        "deposit",
        "withdraw",
        "get_account_info",
        "__str__",
    }


def test_abstract_account_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        AbstractAccount(owner="Алексей")
