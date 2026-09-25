from decimal import Decimal
import pytest

from src.accounts.premium_account import PremiumAccount
from src.enums.account_status import AccountStatus
from src.enums.currency import Currency
from src.exceptions import (
    AccountFrozenError,
    InsufficientFundsError,
    InvalidOperationError,
)


@pytest.fixture
def premium_account() -> PremiumAccount:
    return PremiumAccount(
        owner="Мария",
        balance=1000,
        currency=Currency.RUB,
        status=AccountStatus.ACTIVE,
        account_id="87654321",
        withdrawal_limit=5000,
        overdraft_limit=500,
        fixed_commission=100,
    )


def test_premium_account_creation(
    premium_account: PremiumAccount,
) -> None:
    assert premium_account.owner == "Мария"
    assert premium_account.balance == Decimal("1000")
    assert premium_account.currency is Currency.RUB
    assert premium_account.status is AccountStatus.ACTIVE
    assert premium_account.account_id == "87654321"
    assert premium_account.withdrawal_limit == Decimal("5000")
    assert premium_account.overdraft_limit == Decimal("500")
    assert premium_account.fixed_commission == Decimal("100")


@pytest.mark.parametrize(
    "withdrawal_limit",
    [
        0,
        -1,
        True,
        "5000",
    ],
)
def test_invalid_withdrawal_limit(
    withdrawal_limit: object,
) -> None:
    with pytest.raises(InvalidOperationError):
        PremiumAccount(
            owner="Мария",
            balance=1000,
            withdrawal_limit=withdrawal_limit,
            overdraft_limit=500,
            fixed_commission=100,
        )


@pytest.mark.parametrize(
    "overdraft_limit",
    [
        -1,
        True,
        "500",
    ],
)
def test_invalid_overdraft_limit(
    overdraft_limit: object,
) -> None:
    with pytest.raises(InvalidOperationError):
        PremiumAccount(
            owner="Мария",
            balance=1000,
            withdrawal_limit=5000,
            overdraft_limit=overdraft_limit,
            fixed_commission=100,
        )


@pytest.mark.parametrize(
    "fixed_commission",
    [
        -1,
        True,
        "100",
    ],
)
def test_invalid_fixed_commission(
    fixed_commission: object,
) -> None:
    with pytest.raises(InvalidOperationError):
        PremiumAccount(
            owner="Мария",
            balance=1000,
            withdrawal_limit=5000,
            overdraft_limit=500,
            fixed_commission=fixed_commission,
        )


def test_withdraw_charges_fixed_commission(
    premium_account: PremiumAccount,
) -> None:
    result = premium_account.withdraw(400)

    assert result == Decimal("500")
    assert premium_account.balance == Decimal("500")


def test_withdraw_uses_overdraft(
    premium_account: PremiumAccount,
) -> None:
    result = premium_account.withdraw(1200)

    assert result == Decimal("-300")
    assert premium_account.balance == Decimal("-300")


def test_withdraw_allows_exact_overdraft_limit(
    premium_account: PremiumAccount,
) -> None:
    result = premium_account.withdraw(1400)

    assert result == Decimal("-500")
    assert premium_account.balance == Decimal("-500")


def test_withdraw_rejects_exceeded_overdraft(
    premium_account: PremiumAccount,
) -> None:
    with pytest.raises(InsufficientFundsError):
        premium_account.withdraw(1401)

    assert premium_account.balance == Decimal("1000")


def test_withdraw_rejects_exceeded_withdrawal_limit(
    premium_account: PremiumAccount,
) -> None:
    with pytest.raises(InvalidOperationError):
        premium_account.withdraw(5001)

    assert premium_account.balance == Decimal("1000")


def test_frozen_premium_account_rejects_withdrawal() -> None:
    account = PremiumAccount(
        owner="Мария",
        balance=1000,
        status=AccountStatus.FROZEN,
        withdrawal_limit=5000,
        overdraft_limit=500,
        fixed_commission=100,
    )

    with pytest.raises(AccountFrozenError):
        account.withdraw(100)

    assert account.balance == Decimal("1000")


def test_premium_account_info(
    premium_account: PremiumAccount,
) -> None:
    assert premium_account.get_account_info() == {
        "account_type": "PremiumAccount",
        "account_id": "87654321",
        "owner": "Мария",
        "status": "active",
        "balance": "1000.00",
        "currency": "RUB",
        "withdrawal_limit": "5000.00",
        "overdraft_limit": "500.00",
        "fixed_commission": "100.00",
    }


def test_premium_account_string(
    premium_account: PremiumAccount,
) -> None:
    assert str(premium_account) == (
        "PremiumAccount | "
        "Клиент: Мария | "
        "Счёт: ****4321 | "
        "Статус: active | "
        "Баланс: 1000.00 RUB | "
        "Лимит снятия: 5000.00 RUB | "
        "Овердрафт: 500.00 RUB | "
        "Комиссия: 100.00 RUB"
    )
