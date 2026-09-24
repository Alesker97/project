from src.accounts.bank_account import BankAccount
from src.enums.account_status import AccountStatus
from src.enums.currency import Currency
from src.exceptions import BankingError


def main() -> None:
    active_account = BankAccount(
        owner="Алексей",
        balance=1000,
        currency=Currency.RUB,
        status=AccountStatus.ACTIVE,
    )
    frozen_account = BankAccount(
        owner="Мария",
        balance=500,
        currency=Currency.USD,
        status=AccountStatus.FROZEN,
    )

    print("Созданные счета:")
    print(active_account)
    print(frozen_account)

    print("\nОперации по активному счёту:")
    balance = active_account.deposit(500)
    print(f"После пополнения: {balance:.2f} {active_account.currency.value}")

    balance = active_account.withdraw(300)
    print(f"После снятия: {balance:.2f} {active_account.currency.value}")

    print("\nОперации по замороженному счёту:")
    try:
        frozen_account.deposit(100)
    except BankingError as error:
        print(f"Ошибка пополнения: {error}")

    try:
        frozen_account.withdraw(100)
    except BankingError as error:
        print(f"Ошибка снятия: {error}")

    print("\nИтоговое состояние счетов:")
    print(active_account)
    print(frozen_account)


if __name__ == "__main__":
    main()
