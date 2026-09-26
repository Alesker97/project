from datetime import datetime
from decimal import Decimal

from src.accounts.bank_account import BankAccount
from src.accounts.investment_account import InvestmentAccount
from src.accounts.premium_account import PremiumAccount
from src.accounts.savings_account import SavingsAccount
from src.banks.bank import Bank
from src.clients.client import Client
from src.enums.account_status import AccountStatus
from src.enums.asset_type import AssetType
from src.enums.currency import Currency
from src.exceptions import BankingError


def create_demo_bank() -> tuple[Bank, list[Client]]:
    bank = Bank(
        time_provider=lambda: datetime(
            2026,
            9,
            26,
            12,
            0,
        )
    )

    alexey = Client(
        full_name="Алексей Иванов",
        client_id="client-001",
        age=30,
        contacts={
            "phone": "+994501111111",
            "email": "alexey@example.com",
        },
    )
    maria = Client(
        full_name="Мария Петрова",
        client_id="client-002",
        age=25,
        contacts={
            "phone": "+994502222222",
            "email": "maria@example.com",
        },
    )
    ivan = Client(
        full_name="Иван Сидоров",
        client_id="client-003",
        age=40,
        contacts={
            "phone": "+994503333333",
            "email": "ivan@example.com",
        },
    )

    bank.add_client(alexey, "alexey-password")
    bank.add_client(maria, "maria-password")
    bank.add_client(ivan, "ivan-password")

    savings_account = SavingsAccount(
        owner=alexey.full_name,
        balance=10000,
        currency=Currency.RUB,
        account_id="savings-001",
        min_balance=1000,
        monthly_interest_rate=0.01,
    )
    premium_account = PremiumAccount(
        owner=maria.full_name,
        balance=5000,
        currency=Currency.RUB,
        account_id="premium-001",
        withdrawal_limit=50000,
        overdraft_limit=5000,
        fixed_commission=100,
    )
    investment_account = InvestmentAccount(
        owner=ivan.full_name,
        balance=30000,
        currency=Currency.USD,
        account_id="investment-001",
    )

    bank.open_account(alexey.client_id, savings_account)
    bank.open_account(maria.client_id, premium_account)
    bank.open_account(ivan.client_id, investment_account)

    savings_account.apply_monthly_interest()
    premium_account.withdraw(3000)
    investment_account.invest(AssetType.STOCKS, 10000)
    investment_account.invest(AssetType.BONDS, 5000)
    investment_account.invest(AssetType.ETF, 5000)

    growth_rates = {
        AssetType.STOCKS: Decimal("0.10"),
        AssetType.BONDS: Decimal("0.04"),
        AssetType.ETF: Decimal("0.07"),
    }
    projected_growth = investment_account.project_yearly_growth(
        growth_rates
    )

    print(
        f"Прогнозируемый прирост портфеля: "
        f"{projected_growth:.2f} "
        f"{investment_account.currency.value}"
    )

    return bank, [alexey, maria, ivan]

def demonstrate_authentication(
    bank: Bank,
    clients: list[Client],
) -> None:
    alexey, maria, _ = clients

    successful_login = bank.authenticate_client(
        alexey.client_id,
        "alexey-password",
    )
    print(f"Успешный вход Алексея: {successful_login}")

    for attempt_number in range(1, 4):
        result = bank.authenticate_client(
            maria.client_id,
            "wrong-password",
        )
        print(
            f"Неудачный вход Марии №{attempt_number}: {result}"
        )

    print(f"Статус Марии: {maria.status.value}")

def demonstrate_account_management(bank: Bank) -> None:
    bank.freeze_account("savings-001")
    frozen_account = bank.search_accounts(
        status=AccountStatus.FROZEN
    )[0]
    print(
        f"Статус после заморозки: "
        f"{frozen_account.status.value}"
    )

    bank.unfreeze_account("savings-001")
    print(
        f"Статус после разморозки: "
        f"{frozen_account.status.value}"
    )

def display_accounts(bank: Bank) -> None:
    print("\nСчета банка:\n")

    for account in bank.search_accounts():
        print(account)
        print(account.get_account_info())
        print()

def display_analytics(bank: Bank) -> None:
    print("Общие балансы:")

    for currency, balance in bank.get_total_balance().items():
        if balance != 0:
            print(f"{currency.value}: {balance:.2f}")

    print("\nРейтинг клиентов в RUB:")

    for position, ranking_item in enumerate(
        bank.get_clients_ranking(Currency.RUB),
        start=1,
    ):
        client, balance = ranking_item
        print(
            f"{position}. {client.full_name}: "
            f"{balance:.2f} RUB"
        )

def display_suspicious_actions(bank: Bank) -> None:
    print("\nПодозрительные действия:")

    for action in bank.suspicious_actions:
        print(action)

def demonstrate_night_restriction() -> None:
    bank = Bank(
        time_provider=lambda: datetime(
            2026,
            9,
            26,
            2,
            0,
        )
    )
    client = Client(
        full_name="Ночной клиент",
        client_id="client-night",
        age=30,
        contacts={"phone": "+994504444444"},
    )
    account = BankAccount(
        owner=client.full_name,
        balance=1000,
        account_id="night-account",
    )

    bank.add_client(client, "night-password")

    try:
        bank.open_account(client.client_id, account)
    except BankingError as error:
        print(f"\nНочная операция отклонена: {error}")

    print(bank.suspicious_actions)

def main() -> None:
    bank, clients = create_demo_bank()

    demonstrate_authentication(bank, clients)
    demonstrate_account_management(bank)
    display_accounts(bank)
    display_analytics(bank)
    display_suspicious_actions(bank)
    demonstrate_night_restriction()


if __name__ == "__main__":
    main()
