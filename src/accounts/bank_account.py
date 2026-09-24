from decimal import Decimal

from src.accounts.account_base import AbstractAccount
from src.enums.account_status import AccountStatus
from src.enums.currency import Currency
from src.exceptions import InsufficientFundsError, InvalidOperationError


class BankAccount(AbstractAccount):
    def __init__(
        self,
        owner: str,
        balance: Decimal | int | float = 0,
        currency: Currency = Currency.RUB,
        status: AccountStatus = AccountStatus.ACTIVE,
        account_id: str | None = None,
    ) -> None:
        super().__init__(
            owner=owner,
            balance=balance,
            status=status,
            account_id=account_id,
        )
        self._currency = self._validate_currency(currency)

    @property
    def currency(self) -> Currency:
        return self._currency

    @staticmethod
    def _validate_currency(currency: Currency) -> Currency:
        if not isinstance(currency, Currency):
            raise InvalidOperationError(
                "Передана неподдерживаемая валюта."
            )

        return currency

    def deposit(
        self,
        amount: Decimal | int | float,
    ) -> Decimal:
        decimal_amount = self._validate_amount(amount)
        self._ensure_operations_allowed()
        self._balance += decimal_amount

        return self._balance

    def withdraw(
        self,
        amount: Decimal | int | float,
    ) -> Decimal:
        decimal_amount = self._validate_amount(amount)
        self._ensure_operations_allowed()

        if decimal_amount > self._balance:
            raise InsufficientFundsError(
                f"Недостаточно средств: доступно "
                f"{self._balance:.2f} {self._currency.value}, "
                f"запрошено {decimal_amount:.2f} "
                f"{self._currency.value}."
            )

        self._balance -= decimal_amount

        return self._balance

    def get_account_info(self) -> dict[str, object]:
        return {
            "account_type": self.__class__.__name__,
            "account_id": self._account_id,
            "owner": self._owner,
            "status": self._status.value,
            "balance": f"{self._balance:.2f}",
            "currency": self._currency.value,
        }

    def __str__(self) -> str:
        return (
            f"{self.__class__.__name__} | "
            f"Клиент: {self._owner} | "
            f"Счёт: {self._get_masked_account_id()} | "
            f"Статус: {self._status.value} | "
            f"Баланс: {self._balance:.2f} {self._currency.value}"
        )
