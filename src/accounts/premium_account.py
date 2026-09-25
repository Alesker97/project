from decimal import Decimal

from src.accounts.bank_account import BankAccount
from src.enums.account_status import AccountStatus
from src.enums.currency import Currency
from src.exceptions import InsufficientFundsError, InvalidOperationError


class PremiumAccount(BankAccount):
    def __init__(
        self,
        owner: str,
        balance: Decimal | int | float = 0,
        currency: Currency = Currency.RUB,
        status: AccountStatus = AccountStatus.ACTIVE,
        account_id: str | None = None,
        *,
        withdrawal_limit: Decimal | int | float,
        overdraft_limit: Decimal | int | float,
        fixed_commission: Decimal | int | float,
    ) -> None:
        withdrawal_limit_value = self._convert_to_decimal(
            withdrawal_limit
        )
        overdraft_limit_value = self._convert_to_decimal(
            overdraft_limit
        )
        fixed_commission_value = self._convert_to_decimal(
            fixed_commission
        )

        if withdrawal_limit_value <= 0:
            raise InvalidOperationError(
                "Лимит снятия должен быть больше нуля."
            )

        if overdraft_limit_value < 0:
            raise InvalidOperationError(
                "Лимит овердрафта не может быть отрицательным."
            )

        if fixed_commission_value < 0:
            raise InvalidOperationError(
                "Фиксированная комиссия не может быть отрицательной."
            )

        super().__init__(
            owner=owner,
            balance=balance,
            currency=currency,
            status=status,
            account_id=account_id,
        )

        self._withdrawal_limit = withdrawal_limit_value
        self._overdraft_limit = overdraft_limit_value
        self._fixed_commission = fixed_commission_value

    @property
    def withdrawal_limit(self) -> Decimal:
        return self._withdrawal_limit

    @property
    def overdraft_limit(self) -> Decimal:
        return self._overdraft_limit

    @property
    def fixed_commission(self) -> Decimal:
        return self._fixed_commission

    def withdraw(
        self,
        amount: Decimal | int | float,
    ) -> Decimal:
        decimal_amount = self._validate_amount(amount)
        self._ensure_operations_allowed()

        if decimal_amount > self._withdrawal_limit:
            raise InvalidOperationError(
                f"Сумма снятия превышает лимит "
                f"{self._withdrawal_limit:.2f} "
                f"{self._currency.value}."
            )

        total_debit = decimal_amount + self._fixed_commission
        available_funds = self._balance + self._overdraft_limit

        if total_debit > available_funds:
            raise InsufficientFundsError(
                "Недостаточно средств с учётом доступного овердрафта."
            )

        self._balance -= total_debit

        return self._balance

    def get_account_info(self) -> dict[str, object]:
        account_info = super().get_account_info()
        account_info.update(
            {
                "withdrawal_limit": f"{self._withdrawal_limit:.2f}",
                "overdraft_limit": f"{self._overdraft_limit:.2f}",
                "fixed_commission": f"{self._fixed_commission:.2f}",
            }
        )

        return account_info

    def __str__(self) -> str:
        return (
            f"{super().__str__()} | "
            f"Лимит снятия: {self._withdrawal_limit:.2f} "
            f"{self._currency.value} | "
            f"Овердрафт: {self._overdraft_limit:.2f} "
            f"{self._currency.value} | "
            f"Комиссия: {self._fixed_commission:.2f} "
            f"{self._currency.value}"
        )
