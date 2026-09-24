from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from src.enums.account_status import AccountStatus
from src.exceptions import (
    AccountClosedError,
    AccountFrozenError,
    InvalidOperationError,
)


class AbstractAccount(ABC):
    def __init__(
        self,
        owner: str,
        balance: Decimal | int | float = 0,
        status: AccountStatus = AccountStatus.ACTIVE,
        account_id: str | None = None,
    ) -> None:
        self._owner = self._validate_owner(owner)
        self._balance = self._validate_initial_balance(balance)
        self._status = self._validate_status(status)
        self._account_id = self._validate_or_generate_account_id(account_id)

    @property
    def account_id(self) -> str:
        return self._account_id

    @property
    def owner(self) -> str:
        return self._owner

    @property
    def balance(self) -> Decimal:
        return self._balance

    @property
    def status(self) -> AccountStatus:
        return self._status

    @staticmethod
    def _validate_owner(owner: str) -> str:
        if not isinstance(owner, str) or not owner.strip():
            raise InvalidOperationError(
                "Владелец счёта должен быть непустой строкой."
            )

        return owner.strip()

    @staticmethod
    def _convert_to_decimal(
        value: Decimal | int | float,
    ) -> Decimal:
        if isinstance(value, bool) or not isinstance(
            value,
            (Decimal, int, float),
        ):
            raise InvalidOperationError(
                "Денежное значение должно быть числом."
            )

        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as error:
            raise InvalidOperationError(
                "Не удалось преобразовать денежное значение."
            ) from error

        if not decimal_value.is_finite():
            raise InvalidOperationError(
                "Денежное значение должно быть конечным числом."
            )

        return decimal_value

    @classmethod
    def _validate_initial_balance(
        cls,
        balance: Decimal | int | float,
    ) -> Decimal:
        decimal_balance = cls._convert_to_decimal(balance)

        if decimal_balance < 0:
            raise InvalidOperationError(
                "Начальный баланс не может быть отрицательным."
            )

        return decimal_balance

    @staticmethod
    def _validate_status(
        status: AccountStatus,
    ) -> AccountStatus:
        if not isinstance(status, AccountStatus):
            raise InvalidOperationError(
                "Передан недопустимый статус счёта."
            )

        return status

    @staticmethod
    def _validate_or_generate_account_id(
        account_id: str | None,
    ) -> str:
        if account_id is None:
            return uuid4().hex[:8]

        if not isinstance(account_id, str):
            raise InvalidOperationError(
                "Идентификатор счёта должен быть строкой."
            )

        normalized_account_id = account_id.strip()

        if len(normalized_account_id) < 4:
            raise InvalidOperationError(
                "Идентификатор счёта должен содержать минимум 4 символа."
            )

        return normalized_account_id

    @classmethod
    def _validate_amount(
        cls,
        amount: Decimal | int | float,
    ) -> Decimal:
        decimal_amount = cls._convert_to_decimal(amount)

        if decimal_amount <= 0:
            raise InvalidOperationError(
                "Сумма операции должна быть больше нуля."
            )

        return decimal_amount

    def _ensure_operations_allowed(self) -> None:
        if self._status is AccountStatus.FROZEN:
            raise AccountFrozenError(
                "Операция запрещена: счёт заморожен."
            )

        if self._status is AccountStatus.CLOSED:
            raise AccountClosedError(
                "Операция запрещена: счёт закрыт."
            )

    def _get_masked_account_id(self) -> str:
        return f"****{self._account_id[-4:]}"

    @abstractmethod
    def deposit(
        self,
        amount: Decimal | int | float,
    ) -> Decimal:
        pass

    @abstractmethod
    def withdraw(
        self,
        amount: Decimal | int | float,
    ) -> Decimal:
        pass

    @abstractmethod
    def get_account_info(self) -> dict[str, object]:
        pass

    @abstractmethod
    def __str__(self) -> str:
        pass
