from decimal import Decimal
import pytest

from src.accounts.bank_account import BankAccount
from src.enums.account_status import AccountStatus
from src.enums.currency import Currency
from src.exceptions import (
    AccountClosedError,
    AccountFrozenError,
    InsufficientFundsError,
    InvalidOperationError,
)


@pytest.fixture
def active_account() -> BankAccount:
    return BankAccount(
        owner="Алексей",
        balance=1000,
        currency=Currency.RUB,
        status=AccountStatus.ACTIVE,
        account_id="12345678",
    )


def test_account_creation(active_account: BankAccount) -> None:
    assert active_account.owner == "Алексей"
    assert active_account.balance == Decimal("1000")
    assert active_account.currency is Currency.RUB
    assert active_account.status is AccountStatus.ACTIVE
    assert active_account.account_id == "12345678"


def test_account_id_is_generated() -> None:
    account = BankAccount(owner="Алексей")

    assert len(account.account_id) == 8
    int(account.account_id, 16)


def test_deposit(active_account: BankAccount) -> None:
    result = active_account.deposit(500)

    assert result == Decimal("1500")
    assert active_account.balance == Decimal("1500")


def test_withdraw(active_account: BankAccount) -> None:
    result = active_account.withdraw(400)

    assert result == Decimal("600")
    assert active_account.balance == Decimal("600")


@pytest.mark.parametrize(
    "amount",
    [
        0,
        -100,
        True,
        "100",
        None,
        float("nan"),
        float("inf"),
    ],
)
def test_invalid_deposit_amount(
    active_account: BankAccount,
    amount: object,
) -> None:
    with pytest.raises(InvalidOperationError):
        active_account.deposit(amount)


@pytest.mark.parametrize(
    "operation_name",
    [
        "deposit",
        "withdraw",
    ],
)
def test_frozen_account_rejects_operations(
    operation_name: str,
) -> None:
    account = BankAccount(
        owner="Алексей",
        balance=1000,
        status=AccountStatus.FROZEN,
    )
    operation = getattr(account, operation_name)

    with pytest.raises(AccountFrozenError):
        operation(100)


@pytest.mark.parametrize(
    "operation_name",
    [
        "deposit",
        "withdraw",
    ],
)
def test_closed_account_rejects_operations(
    operation_name: str,
) -> None:
    account = BankAccount(
        owner="Алексей",
        balance=1000,
        status=AccountStatus.CLOSED,
    )
    operation = getattr(account, operation_name)

    with pytest.raises(AccountClosedError):
        operation(100)


def test_withdraw_rejects_insufficient_funds(
    active_account: BankAccount,
) -> None:
    with pytest.raises(InsufficientFundsError):
        active_account.withdraw(1500)


@pytest.mark.parametrize(
    "owner",
    [
        "",
        "   ",
        None,
    ],
)
def test_invalid_owner(owner: object) -> None:
    with pytest.raises(InvalidOperationError):
        BankAccount(owner=owner)


def test_negative_initial_balance_is_rejected() -> None:
    with pytest.raises(InvalidOperationError):
        BankAccount(owner="Алексей", balance=-100)


def test_invalid_status_is_rejected() -> None:
    with pytest.raises(InvalidOperationError):
        BankAccount(
            owner="Алексей",
            status="active",
        )


def test_invalid_currency_is_rejected() -> None:
    with pytest.raises(InvalidOperationError):
        BankAccount(
            owner="Алексей",
            currency="GBP",
        )


def test_get_account_info(active_account: BankAccount) -> None:
    assert active_account.get_account_info() == {
        "account_type": "BankAccount",
        "account_id": "12345678",
        "owner": "Алексей",
        "status": "active",
        "balance": "1000.00",
        "currency": "RUB",
    }


def test_string_representation(active_account: BankAccount) -> None:
    assert str(active_account) == (
        "BankAccount | "
        "Клиент: Алексей | "
        "Счёт: ****5678 | "
        "Статус: active | "
        "Баланс: 1000.00 RUB"
    )
