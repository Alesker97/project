from datetime import datetime
from decimal import Decimal
from decimal import InvalidOperation as DecimalInvalidOperation
from uuid import uuid4

from src.accounts.account_base import AbstractAccount
from src.enums.currency import Currency
from src.enums.transaction_status import TransactionStatus
from src.enums.transaction_type import TransactionType
from src.exceptions import InvalidOperationError


class Transaction:
    def __init__(
        self,
        transaction_type: TransactionType,
        amount: Decimal | int | float | str,
        currency: Currency,
        sender: AbstractAccount,
        recipient: AbstractAccount,
        transaction_id: str | None = None,
        created_at: datetime | None = None,
        scheduled_at: datetime | None = None,
    ) -> None:
        self._transaction_id = self._create_transaction_id(
            transaction_id
        )
        self._transaction_type = self._validate_transaction_type(
            transaction_type
        )
        self._amount = self._validate_positive_amount(amount)
        self._currency = self._validate_currency(currency)
        self._sender = self._validate_account(sender, "отправитель")
        self._recipient = self._validate_account(
            recipient,
            "получатель",
        )
        self._validate_different_accounts()
        self._commission = Decimal("0.00")
        self._status = TransactionStatus.PENDING
        self._failure_reason: str | None = None
        self._created_at = self._validate_timestamp(
            created_at or datetime.now()
        )
        self._scheduled_at = self._validate_timestamp(
            scheduled_at or self._created_at
        )
        self._validate_schedule()
        self._processed_at: datetime | None = None
        self._attempts = 0

    @property
    def transaction_id(self) -> str:
        return self._transaction_id

    @property
    def transaction_type(self) -> TransactionType:
        return self._transaction_type

    @property
    def amount(self) -> Decimal:
        return self._amount

    @property
    def currency(self) -> Currency:
        return self._currency

    @property
    def commission(self) -> Decimal:
        return self._commission

    @property
    def sender(self) -> AbstractAccount:
        return self._sender

    @property
    def recipient(self) -> AbstractAccount:
        return self._recipient

    @property
    def status(self) -> TransactionStatus:
        return self._status

    @property
    def failure_reason(self) -> str | None:
        return self._failure_reason

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def scheduled_at(self) -> datetime:
        return self._scheduled_at

    @property
    def processed_at(self) -> datetime | None:
        return self._processed_at

    @property
    def attempts(self) -> int:
        return self._attempts

    def _set_commission(
        self,
        commission: Decimal | int | float | str,
    ) -> None:
        self._commission = self._validate_non_negative_amount(
            commission
        )

    def _increment_attempts(self) -> None:
        self._attempts += 1

    def _mark_processing(self) -> None:
        self._status = TransactionStatus.PROCESSING
        self._failure_reason = None

    def _mark_completed(self, processed_at: datetime) -> None:
        self._status = TransactionStatus.COMPLETED
        self._failure_reason = None
        self._processed_at = self._validate_timestamp(processed_at)

    def _mark_failed(
        self,
        reason: str,
        processed_at: datetime,
    ) -> None:
        self._status = TransactionStatus.FAILED
        self._failure_reason = self._validate_reason(reason)
        self._processed_at = self._validate_timestamp(processed_at)

    def _mark_cancelled(
        self,
        reason: str,
        processed_at: datetime,
    ) -> None:
        self._status = TransactionStatus.CANCELLED
        self._failure_reason = self._validate_reason(reason)
        self._processed_at = self._validate_timestamp(processed_at)

    @staticmethod
    def _create_transaction_id(
        transaction_id: str | None,
    ) -> str:
        if transaction_id is None:
            return uuid4().hex[:8]
        if not isinstance(transaction_id, str):
            raise InvalidOperationError(
                "ID транзакции должен быть строкой."
            )
        transaction_id = transaction_id.strip()
        if not transaction_id:
            raise InvalidOperationError(
                "ID транзакции не может быть пустым."
            )
        return transaction_id

    @staticmethod
    def _validate_transaction_type(
        transaction_type: TransactionType,
    ) -> TransactionType:
        if not isinstance(transaction_type, TransactionType):
            raise InvalidOperationError(
                "Указан недопустимый тип транзакции."
            )
        return transaction_type

    @staticmethod
    def _validate_currency(currency: Currency) -> Currency:
        if not isinstance(currency, Currency):
            raise InvalidOperationError(
                "Указана недопустимая валюта транзакции."
            )
        return currency

    @staticmethod
    def _validate_account(
        account: AbstractAccount,
        role: str,
    ) -> AbstractAccount:
        if not isinstance(account, AbstractAccount):
            raise InvalidOperationError(
                f"Некорректный счёт: {role}."
            )
        return account

    @staticmethod
    def _validate_positive_amount(
        amount: Decimal | int | float | str,
    ) -> Decimal:
        value = Transaction._convert_amount(amount)
        if value <= 0:
            raise InvalidOperationError(
                "Сумма транзакции должна быть больше нуля."
            )
        return value

    @staticmethod
    def _validate_non_negative_amount(
        amount: Decimal | int | float | str,
    ) -> Decimal:
        value = Transaction._convert_amount(amount)
        if value < 0:
            raise InvalidOperationError(
                "Комиссия не может быть отрицательной."
            )
        return value

    @staticmethod
    def _convert_amount(
        amount: Decimal | int | float | str,
    ) -> Decimal:
        if isinstance(amount, bool):
            raise InvalidOperationError(
                "Сумма должна быть числом."
            )
        try:
            value = Decimal(str(amount))
        except (DecimalInvalidOperation, TypeError, ValueError) as error:
            raise InvalidOperationError(
                "Сумма должна быть числом."
            ) from error
        if not value.is_finite():
            raise InvalidOperationError(
                "Сумма должна быть конечным числом."
            )
        return value

    @staticmethod
    def _validate_timestamp(timestamp: datetime) -> datetime:
        if not isinstance(timestamp, datetime):
            raise InvalidOperationError(
                "Время транзакции должно иметь тип datetime."
            )
        return timestamp

    @staticmethod
    def _validate_reason(reason: str) -> str:
        if not isinstance(reason, str) or not reason.strip():
            raise InvalidOperationError(
                "Причина завершения должна быть указана."
            )
        return reason.strip()

    def _validate_different_accounts(self) -> None:
        if self._sender.account_id == self._recipient.account_id:
            raise InvalidOperationError(
                "Отправитель и получатель должны быть разными счетами."
            )

    def _validate_schedule(self) -> None:
        if self._scheduled_at < self._created_at:
            raise InvalidOperationError(
                "Отложенная операция не может быть назначена "
                "раньше создания транзакции."
            )
