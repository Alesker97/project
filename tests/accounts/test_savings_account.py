from decimal import Decimal
import pytest

from src.accounts.savings_account import SavingsAccount
from src.enums.account_status import AccountStatus
from src.enums.currency import Currency
from src.exceptions import (
    AccountFrozenError,
    InsufficientFundsError,
    InvalidOperationError,
)


@pytest.fixture
def savings_account() -> SavingsAccount:
    return SavingsAccount(
        owner="Алексей",
        balance=10000,
        currency=Currency.RUB,
        status=AccountStatus.ACTIVE,
        account_id="12345678",
        min_balance=1000,
        monthly_interest_rate=0.01,
    )


def test_savings_account_creation(
    savings_account: SavingsAccount,
) -> None:
    assert savings_account.owner == "Алексей"
    assert savings_account.balance == Decimal("10000")
    assert savings_account.currency is Currency.RUB
    assert savings_account.status is AccountStatus.ACTIVE
    assert savings_account.account_id == "12345678"
    assert savings_account.min_balance == Decimal("1000")
    assert savings_account.monthly_interest_rate == Decimal("0.01")


@pytest.mark.parametrize(
    "min_balance",
    [
        -1,
        True,
        "100",
    ],
)
def test_invalid_min_balance(min_balance: object) -> None:
    with pytest.raises(InvalidOperationError):
        SavingsAccount(
            owner="Алексей",
            balance=1000,
            min_balance=min_balance,
            monthly_interest_rate=0.01,
        )


@pytest.mark.parametrize(
    "monthly_interest_rate",
    [
        -0.01,
        True,
        "0.01",
    ],
)
def test_invalid_monthly_interest_rate(
    monthly_interest_rate: object,
) -> None:
    with pytest.raises(InvalidOperationError):
        SavingsAccount(
            owner="Алексей",
            balance=1000,
            min_balance=100,
            monthly_interest_rate=monthly_interest_rate,
        )


def test_initial_balance_below_minimum_is_rejected() -> None:
    with pytest.raises(InvalidOperationError):
        SavingsAccount(
            owner="Алексей",
            balance=500,
            min_balance=1000,
            monthly_interest_rate=0.01,
        )


def test_withdraw_preserves_minimum_balance(
    savings_account: SavingsAccount,
) -> None:
    result = savings_account.withdraw(9000)

    assert result == Decimal("1000")
    assert savings_account.balance == Decimal("1000")


def test_withdraw_below_minimum_is_rejected(
    savings_account: SavingsAccount,
) -> None:
    with pytest.raises(InsufficientFundsError):
        savings_account.withdraw(9001)

    assert savings_account.balance == Decimal("10000")


def test_apply_monthly_interest(
    savings_account: SavingsAccount,
) -> None:
    result = savings_account.apply_monthly_interest()

    assert result == Decimal("10100.00")
    assert savings_account.balance == Decimal("10100.00")


def test_frozen_account_rejects_interest() -> None:
    account = SavingsAccount(
        owner="Алексей",
        balance=10000,
        status=AccountStatus.FROZEN,
        min_balance=1000,
        monthly_interest_rate=0.01,
    )

    with pytest.raises(AccountFrozenError):
        account.apply_monthly_interest()

    assert account.balance == Decimal("10000")


def test_savings_account_info(
    savings_account: SavingsAccount,
) -> None:
    assert savings_account.get_account_info() == {
        "account_type": "SavingsAccount",
        "account_id": "12345678",
        "owner": "Алексей",
        "status": "active",
        "balance": "10000.00",
        "currency": "RUB",
        "min_balance": "1000.00",
        "monthly_interest_rate": "0.01",
    }


def test_savings_account_string(
    savings_account: SavingsAccount,
) -> None:
    assert str(savings_account) == (
        "SavingsAccount | "
        "Клиент: Алексей | "
        "Счёт: ****5678 | "
        "Статус: active | "
        "Баланс: 10000.00 RUB | "
        "Мин. остаток: 1000.00 RUB | "
        "Месячная ставка: 1.00%"
    )
