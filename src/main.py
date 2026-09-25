from decimal import Decimal

from src.accounts.account_base import AbstractAccount
from src.accounts.investment_account import InvestmentAccount
from src.accounts.premium_account import PremiumAccount
from src.accounts.savings_account import SavingsAccount
from src.enums.account_status import AccountStatus
from src.enums.asset_type import AssetType
from src.enums.currency import Currency
from src.exceptions import BankingError


def demonstrate_savings_accounts() -> list[AbstractAccount]:
    active_account = SavingsAccount(
        owner="Алексей",
        balance=10000,
        currency=Currency.RUB,
        min_balance=1000,
        monthly_interest_rate=0.01,
    )
    frozen_account = SavingsAccount(
        owner="Мария",
        balance=5000,
        currency=Currency.RUB,
        status=AccountStatus.FROZEN,
        min_balance=2000,
        monthly_interest_rate=0.015,
    )

    active_account.apply_monthly_interest()
    active_account.withdraw(2000)

    try:
        frozen_account.withdraw(500)
    except BankingError as error:
        print(f"Ошибка SavingsAccount: {error}")

    return [active_account, frozen_account]


def demonstrate_premium_accounts() -> list[AbstractAccount]:
    regular_account = PremiumAccount(
        owner="Иван",
        balance=10000,
        currency=Currency.RUB,
        withdrawal_limit=50000,
        overdraft_limit=5000,
        fixed_commission=100,
    )
    overdraft_account = PremiumAccount(
        owner="Анна",
        balance=1000,
        currency=Currency.RUB,
        withdrawal_limit=50000,
        overdraft_limit=5000,
        fixed_commission=100,
    )

    regular_account.withdraw(2000)
    overdraft_account.withdraw(3000)

    return [regular_account, overdraft_account]


def demonstrate_investment_accounts() -> list[AbstractAccount]:
    rub_account = InvestmentAccount(
        owner="Сергей",
        balance=30000,
        currency=Currency.RUB,
    )
    usd_account = InvestmentAccount(
        owner="Елена",
        balance=20000,
        currency=Currency.USD,
    )

    rub_account.invest(AssetType.STOCKS, 10000)
    rub_account.invest(AssetType.BONDS, 5000)
    rub_account.invest(AssetType.ETF, 5000)

    usd_account.invest(AssetType.BONDS, 6000)
    usd_account.invest(AssetType.ETF, 8000)
    usd_account.withdraw(2000)

    growth_rates = {
        AssetType.STOCKS: Decimal("0.10"),
        AssetType.BONDS: Decimal("0.04"),
        AssetType.ETF: Decimal("0.07"),
    }

    rub_growth = rub_account.project_yearly_growth(growth_rates)
    usd_growth = usd_account.project_yearly_growth(growth_rates)

    print(
        f"Прогнозируемый прирост RUB-портфеля: "
        f"{rub_growth:.2f} {rub_account.currency.value}"
    )
    print(
        f"Прогнозируемый прирост USD-портфеля: "
        f"{usd_growth:.2f} {usd_account.currency.value}"
    )

    return [rub_account, usd_account]


def display_accounts(accounts: list[AbstractAccount]) -> None:
    for account in accounts:
        print(account)
        print(account.get_account_info())
        print()


def main() -> None:
    accounts: list[AbstractAccount] = []
    accounts.extend(demonstrate_savings_accounts())
    accounts.extend(demonstrate_premium_accounts())
    accounts.extend(demonstrate_investment_accounts())

    print("\nИтоговое состояние счетов:\n")
    display_accounts(accounts)


if __name__ == "__main__":
    main()
