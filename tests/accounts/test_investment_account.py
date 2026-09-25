from decimal import Decimal
import pytest

from src.accounts.investment_account import InvestmentAccount
from src.enums.account_status import AccountStatus
from src.enums.asset_type import AssetType
from src.enums.currency import Currency
from src.exceptions import (
    AccountFrozenError,
    InsufficientFundsError,
    InvalidOperationError,
)


@pytest.fixture
def investment_account() -> InvestmentAccount:
    return InvestmentAccount(
        owner="Иван",
        balance=30000,
        currency=Currency.RUB,
        status=AccountStatus.ACTIVE,
        account_id="11223344",
    )


def test_investment_account_creation(
    investment_account: InvestmentAccount,
) -> None:
    assert investment_account.owner == "Иван"
    assert investment_account.balance == Decimal("30000")
    assert investment_account.currency is Currency.RUB
    assert investment_account.status is AccountStatus.ACTIVE
    assert investment_account.account_id == "11223344"
    assert investment_account.portfolio == {
        AssetType.STOCKS: Decimal("0"),
        AssetType.BONDS: Decimal("0"),
        AssetType.ETF: Decimal("0"),
    }
    assert investment_account.portfolio_value == Decimal("0")


def test_invest_in_supported_asset(
    investment_account: InvestmentAccount,
) -> None:
    result = investment_account.invest(
        AssetType.STOCKS,
        10000,
    )

    assert result == Decimal("10000")
    assert investment_account.balance == Decimal("20000")
    assert investment_account.portfolio[AssetType.STOCKS] == Decimal(
        "10000"
    )


def test_invest_in_multiple_assets(
    investment_account: InvestmentAccount,
) -> None:
    investment_account.invest(AssetType.STOCKS, 10000)
    investment_account.invest(AssetType.BONDS, 5000)
    investment_account.invest(AssetType.ETF, 5000)

    assert investment_account.balance == Decimal("10000")
    assert investment_account.portfolio == {
        AssetType.STOCKS: Decimal("10000"),
        AssetType.BONDS: Decimal("5000"),
        AssetType.ETF: Decimal("5000"),
    }
    assert investment_account.portfolio_value == Decimal("20000")


def test_unsupported_asset_is_rejected(
    investment_account: InvestmentAccount,
) -> None:
    with pytest.raises(InvalidOperationError):
        investment_account.invest("crypto", 1000)

    assert investment_account.balance == Decimal("30000")


@pytest.mark.parametrize(
    "amount",
    [
        0,
        -100,
        True,
        "1000",
        None,
        float("nan"),
        float("inf"),
    ],
)
def test_invalid_investment_amount(
    investment_account: InvestmentAccount,
    amount: object,
) -> None:
    with pytest.raises(InvalidOperationError):
        investment_account.invest(AssetType.STOCKS, amount)

    assert investment_account.balance == Decimal("30000")


def test_insufficient_investment_funds(
    investment_account: InvestmentAccount,
) -> None:
    with pytest.raises(InsufficientFundsError):
        investment_account.invest(AssetType.STOCKS, 30001)

    assert investment_account.balance == Decimal("30000")
    assert investment_account.portfolio_value == Decimal("0")


def test_frozen_account_rejects_investment() -> None:
    account = InvestmentAccount(
        owner="Иван",
        balance=30000,
        status=AccountStatus.FROZEN,
    )

    with pytest.raises(AccountFrozenError):
        account.invest(AssetType.STOCKS, 1000)

    assert account.balance == Decimal("30000")
    assert account.portfolio_value == Decimal("0")


def test_withdraw_uses_only_free_balance(
    investment_account: InvestmentAccount,
) -> None:
    investment_account.invest(AssetType.STOCKS, 25000)
    result = investment_account.withdraw(5000)

    assert result == Decimal("0")
    assert investment_account.balance == Decimal("0")
    assert investment_account.portfolio_value == Decimal("25000")


def test_withdraw_rejects_invested_funds(
    investment_account: InvestmentAccount,
) -> None:
    investment_account.invest(AssetType.STOCKS, 25000)

    with pytest.raises(InsufficientFundsError):
        investment_account.withdraw(5001)

    assert investment_account.balance == Decimal("5000")
    assert investment_account.portfolio_value == Decimal("25000")


def test_project_yearly_growth(
    investment_account: InvestmentAccount,
) -> None:
    investment_account.invest(AssetType.STOCKS, 10000)
    investment_account.invest(AssetType.BONDS, 5000)
    investment_account.invest(AssetType.ETF, 5000)

    growth_rates = {
        AssetType.STOCKS: Decimal("0.10"),
        AssetType.BONDS: Decimal("0.04"),
        AssetType.ETF: Decimal("0.07"),
    }

    result = investment_account.project_yearly_growth(
        growth_rates
    )

    assert result == Decimal("1550.00")
    assert investment_account.balance == Decimal("10000")
    assert investment_account.portfolio_value == Decimal("20000")


def test_incomplete_growth_rates_are_rejected(
    investment_account: InvestmentAccount,
) -> None:
    growth_rates = {
        AssetType.STOCKS: Decimal("0.10"),
        AssetType.BONDS: Decimal("0.04"),
    }

    with pytest.raises(InvalidOperationError):
        investment_account.project_yearly_growth(growth_rates)


def test_invalid_growth_rate_is_rejected(
    investment_account: InvestmentAccount,
) -> None:
    growth_rates = {
        AssetType.STOCKS: "0.10",
        AssetType.BONDS: Decimal("0.04"),
        AssetType.ETF: Decimal("0.07"),
    }

    with pytest.raises(InvalidOperationError):
        investment_account.project_yearly_growth(growth_rates)


def test_investment_account_info(
    investment_account: InvestmentAccount,
) -> None:
    investment_account.invest(AssetType.STOCKS, 10000)
    investment_account.invest(AssetType.BONDS, 5000)
    investment_account.invest(AssetType.ETF, 5000)

    assert investment_account.get_account_info() == {
        "account_type": "InvestmentAccount",
        "account_id": "11223344",
        "owner": "Иван",
        "status": "active",
        "balance": "10000.00",
        "currency": "RUB",
        "portfolio": {
            "stocks": "10000.00",
            "bonds": "5000.00",
            "etf": "5000.00",
        },
        "portfolio_value": "20000.00",
    }


def test_investment_account_string(
    investment_account: InvestmentAccount,
) -> None:
    investment_account.invest(AssetType.STOCKS, 10000)
    investment_account.invest(AssetType.BONDS, 5000)
    investment_account.invest(AssetType.ETF, 5000)

    assert str(investment_account) == (
        "InvestmentAccount | "
        "Клиент: Иван | "
        "Счёт: ****3344 | "
        "Статус: active | "
        "Баланс: 10000.00 RUB | "
        "Портфель: stocks=10000.00, "
        "bonds=5000.00, "
        "etf=5000.00 RUB | "
        "Стоимость портфеля: 20000.00 RUB"
    )
