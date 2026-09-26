from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from decimal import InvalidOperation as DecimalInvalidOperation
from decimal import ROUND_HALF_UP

from src.accounts.premium_account import PremiumAccount
from src.enums.account_status import AccountStatus
from src.enums.currency import Currency
from src.enums.transaction_status import TransactionStatus
from src.enums.transaction_type import TransactionType
from src.exceptions import AccountClosedError
from src.exceptions import AccountFrozenError
from src.exceptions import InsufficientFundsError
from src.exceptions import InvalidOperationError
from src.transactions.transaction import Transaction
from src.transactions.transaction_queue import TransactionQueue


class TransactionProcessor:
    def __init__(
        self,
        external_commission_rate: Decimal | int | float | str = (
            Decimal("0.01")
        ),
        conversion_rates: dict[
            tuple[Currency, Currency],
            Decimal | int | float | str,
        ] | None = None,
        max_retries: int = 3,
        time_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._external_commission_rate = (
            self._validate_commission_rate(
                external_commission_rate
            )
        )
        self._conversion_rates = self._validate_conversion_rates(
            conversion_rates or {}
        )
        self._max_retries = self._validate_max_retries(max_retries)
        if time_provider is not None and not callable(time_provider):
            raise InvalidOperationError(
                "Источник времени должен быть вызываемым объектом."
            )
        self._time_provider = time_provider or datetime.now
        self._error_log: list[dict[str, object]] = []

    @property
    def external_commission_rate(self) -> Decimal:
        return self._external_commission_rate

    @property
    def conversion_rates(
        self,
    ) -> dict[tuple[Currency, Currency], Decimal]:
        return self._conversion_rates.copy()

    @property
    def max_retries(self) -> int:
        return self._max_retries

    @property
    def error_log(self) -> list[dict[str, object]]:
        return [entry.copy() for entry in self._error_log]

    def process(self, transaction: Transaction) -> bool:
        if not isinstance(transaction, Transaction):
            raise InvalidOperationError(
                "Обработать можно только транзакцию."
            )
        if transaction.status is not TransactionStatus.PENDING:
            raise InvalidOperationError(
                "Обработать можно только ожидающую транзакцию."
            )

        transaction._mark_processing()

        for attempt in range(self._max_retries + 1):
            transaction._increment_attempts()

            try:
                self._execute_transaction(transaction)
            except (
                AccountFrozenError,
                AccountClosedError,
                InsufficientFundsError,
                InvalidOperationError,
            ) as error:
                self._record_error(transaction, error)
                transaction._mark_failed(
                    str(error),
                    self._get_current_time(),
                )
                return False
            except Exception as error:
                self._record_error(transaction, error)

                if attempt == self._max_retries:
                    transaction._mark_failed(
                        str(error),
                        self._get_current_time(),
                    )
                    return False
            else:
                transaction._mark_completed(
                    self._get_current_time()
                )
                return True

        return False

    def process_next(
        self,
        queue: TransactionQueue,
    ) -> Transaction | None:
        queue = self._validate_queue(queue)
        transaction = queue.get_next()

        if transaction is None:
            return None

        self.process(transaction)
        return transaction

    def process_all(
        self,
        queue: TransactionQueue,
    ) -> list[Transaction]:
        queue = self._validate_queue(queue)
        processed_transactions = []

        while True:
            transaction = self.process_next(queue)
            if transaction is None:
                break
            processed_transactions.append(transaction)

        return processed_transactions

    def _execute_transaction(
        self,
        transaction: Transaction,
    ) -> None:
        self._validate_accounts(transaction)
        self._validate_transaction_currency(transaction)

        commission = self._calculate_commission(transaction)
        recipient_amount = self._calculate_recipient_amount(
            transaction
        )

        transaction._set_commission(commission)
        transaction.sender.withdraw(
            transaction.amount + commission
        )
        transaction.recipient.deposit(recipient_amount)

    def _validate_accounts(
        self,
        transaction: Transaction,
    ) -> None:
        self._validate_account_status(
            transaction.sender.status,
            "отправителя",
        )
        self._validate_account_status(
            transaction.recipient.status,
            "получателя",
        )

        if (
            transaction.sender.balance < 0
            and not isinstance(
                transaction.sender,
                PremiumAccount,
            )
        ):
            raise InvalidOperationError(
                "Перевод с отрицательного баланса запрещён."
            )

    @staticmethod
    def _validate_account_status(
        status: AccountStatus,
        role: str,
    ) -> None:
        if status is AccountStatus.FROZEN:
            raise AccountFrozenError(
                f"Счёт {role} заморожен."
            )
        if status is AccountStatus.CLOSED:
            raise AccountClosedError(
                f"Счёт {role} закрыт."
            )

    @staticmethod
    def _validate_transaction_currency(
        transaction: Transaction,
    ) -> None:
        if transaction.currency is not transaction.sender.currency:
            raise InvalidOperationError(
                "Валюта транзакции должна совпадать "
                "с валютой счёта отправителя."
            )

    def _calculate_commission(
        self,
        transaction: Transaction,
    ) -> Decimal:
        if (
            transaction.transaction_type
            is TransactionType.INTERNAL_TRANSFER
        ):
            return Decimal("0.00")

        commission = (
            transaction.amount
            * self._external_commission_rate
        )
        return self._round_money(commission)

    def _calculate_recipient_amount(
        self,
        transaction: Transaction,
    ) -> Decimal:
        if (
            transaction.sender.currency
            is transaction.recipient.currency
        ):
            return transaction.amount

        currency_pair = (
            transaction.sender.currency,
            transaction.recipient.currency,
        )
        conversion_rate = self._conversion_rates.get(currency_pair)

        if conversion_rate is None:
            raise InvalidOperationError(
                "Для валютной пары не установлен курс конвертации."
            )

        converted_amount = transaction.amount * conversion_rate
        return self._round_money(converted_amount)

    def _record_error(
        self,
        transaction: Transaction,
        error: Exception,
    ) -> None:
        self._error_log.append(
            {
                "transaction_id": transaction.transaction_id,
                "attempt": transaction.attempts,
                "error": str(error),
                "timestamp": self._get_current_time(),
            }
        )

    def _get_current_time(self) -> datetime:
        current_time = self._time_provider()
        if not isinstance(current_time, datetime):
            raise InvalidOperationError(
                "Источник времени должен возвращать datetime."
            )
        return current_time

    @staticmethod
    def _validate_queue(
        queue: TransactionQueue,
    ) -> TransactionQueue:
        if not isinstance(queue, TransactionQueue):
            raise InvalidOperationError(
                "Передана некорректная очередь транзакций."
            )
        return queue

    @staticmethod
    def _validate_commission_rate(
        commission_rate: Decimal | int | float | str,
    ) -> Decimal:
        value = TransactionProcessor._convert_decimal(
            commission_rate
        )
        if value < 0 or value > 1:
            raise InvalidOperationError(
                "Ставка комиссии должна быть от 0 до 1."
            )
        return value

    @staticmethod
    def _validate_conversion_rates(
        conversion_rates: dict[
            tuple[Currency, Currency],
            Decimal | int | float | str,
        ],
    ) -> dict[tuple[Currency, Currency], Decimal]:
        if not isinstance(conversion_rates, dict):
            raise InvalidOperationError(
                "Курсы конвертации должны быть словарём."
            )

        validated_rates = {}

        for currency_pair, rate in conversion_rates.items():
            if (
                not isinstance(currency_pair, tuple)
                or len(currency_pair) != 2
                or not all(
                    isinstance(currency, Currency)
                    for currency in currency_pair
                )
            ):
                raise InvalidOperationError(
                    "Указана некорректная валютная пара."
                )

            converted_rate = (
                TransactionProcessor._convert_decimal(rate)
            )
            if converted_rate <= 0:
                raise InvalidOperationError(
                    "Курс конвертации должен быть больше нуля."
                )
            validated_rates[currency_pair] = converted_rate

        return validated_rates

    @staticmethod
    def _validate_max_retries(max_retries: int) -> int:
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or max_retries < 0
        ):
            raise InvalidOperationError(
                "Количество повторных попыток должно быть "
                "неотрицательным целым числом."
            )
        return max_retries

    @staticmethod
    def _convert_decimal(
        value: Decimal | int | float | str,
    ) -> Decimal:
        if isinstance(value, bool):
            raise InvalidOperationError(
                "Значение должно быть числом."
            )
        try:
            converted_value = Decimal(str(value))
        except (
            DecimalInvalidOperation,
            TypeError,
            ValueError,
        ) as error:
            raise InvalidOperationError(
                "Значение должно быть числом."
            ) from error

        if not converted_value.is_finite():
            raise InvalidOperationError(
                "Значение должно быть конечным числом."
            )
        return converted_value

    @staticmethod
    def _round_money(value: Decimal) -> Decimal:
        return value.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
