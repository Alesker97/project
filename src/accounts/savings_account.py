from decimal import Decimal

from src.accounts.bank_account import BankAccount
from src.enums.account_status import AccountStatus
from src.enums.currency import Currency
from src.exceptions import InsufficientFundsError, InvalidOperationError


class SavingsAccount(BankAccount):
    def __init__(
        self,
        owner: str,
        balance: Decimal | int | float = 0,
        currency: Currency = Currency.RUB,
        status: AccountStatus = AccountStatus.ACTIVE,
        account_id: str | None = None,
        *,
        min_balance: Decimal | int | float,
        monthly_interest_rate: Decimal | int | float,
    ) -> None:
        min_balance_value = self._convert_to_decimal(min_balance)
        interest_rate_value = self._convert_to_decimal(
            monthly_interest_rate
        )

        if min_balance_value < 0:
            raise InvalidOperationError(
                "Минимальный остаток не может быть отрицательным."
            )

        if interest_rate_value < 0:
            raise InvalidOperationError(
                "Месячная ставка не может быть отрицательной."
            )

        super().__init__(
            owner=owner,
            balance=balance,
            currency=currency,
            status=status,
            account_id=account_id,
        )

        if self._balance < min_balance_value:
            raise InvalidOperationError(
                "Начальный баланс не может быть меньше "
                "минимального остатка."
            )

        self._min_balance = min_balance_value
        self._monthly_interest_rate = interest_rate_value

    @property
    def min_balance(self) -> Decimal:
        return self._min_balance

    @property
    def monthly_interest_rate(self) -> Decimal:
        return self._monthly_interest_rate

    def withdraw(
        self,
        amount: Decimal | int | float,
    ) -> Decimal:
        decimal_amount = self._validate_amount(amount)
        self._ensure_operations_allowed()
        new_balance = self._balance - decimal_amount

        if new_balance < self._min_balance:
            raise InsufficientFundsError(
                f"После снятия баланс не может быть меньше "
                f"{self._min_balance:.2f} {self._currency.value}."
            )

        self._balance = new_balance

        return self._balance

    def apply_monthly_interest(self) -> Decimal:
        self._ensure_operations_allowed()
        interest = self._balance * self._monthly_interest_rate
        self._balance += interest

        return self._balance

    def get_account_info(self) -> dict[str, object]:
        account_info = super().get_account_info()
        account_info.update(
            {
                "min_balance": f"{self._min_balance:.2f}",
                "monthly_interest_rate": str(
                    self._monthly_interest_rate
                ),
            }
        )

        return account_info

    def __str__(self) -> str:
        interest_rate_percent = (
            self._monthly_interest_rate * Decimal("100")
        )

        return (
            f"{super().__str__()} | "
            f"Мин. остаток: {self._min_balance:.2f} "
            f"{self._currency.value} | "
            f"Месячная ставка: {interest_rate_percent:.2f}%"
        )
