from collections.abc import Callable
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from decimal import InvalidOperation as DecimalInvalidOperation

from src.audit.audit_log import AuditLog
from src.enums.risk_level import RiskLevel
from src.exceptions import InvalidOperationError
from src.transactions.transaction import Transaction


class RiskAnalyzer:
    def __init__(
        self,
        large_amount_threshold: Decimal | int | float | str = (
            Decimal("10000")
        ),
        frequent_operations_limit: int = 3,
        frequent_operations_window: timedelta = timedelta(
            minutes=5
        ),
        time_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._large_amount_threshold = (
            self._validate_large_amount_threshold(
                large_amount_threshold
            )
        )
        self._frequent_operations_limit = (
            self._validate_frequent_operations_limit(
                frequent_operations_limit
            )
        )
        self._frequent_operations_window = (
            self._validate_frequent_operations_window(
                frequent_operations_window
            )
        )
        if time_provider is not None and not callable(time_provider):
            raise InvalidOperationError(
                "Источник времени должен быть вызываемым объектом."
            )
        self._time_provider = time_provider or datetime.now

    @property
    def large_amount_threshold(self) -> Decimal:
        return self._large_amount_threshold

    @property
    def frequent_operations_limit(self) -> int:
        return self._frequent_operations_limit

    @property
    def frequent_operations_window(self) -> timedelta:
        return self._frequent_operations_window

    def analyze(
        self,
        transaction: Transaction,
        client_id: str,
        audit_log: AuditLog,
    ) -> dict[str, object]:
        transaction = self._validate_transaction(transaction)
        client_id = self._validate_client_id(client_id)
        audit_log = self._validate_audit_log(audit_log)
        current_time = self._get_current_time()
        reasons = []

        if transaction.amount >= self._large_amount_threshold:
            reasons.append("large_amount")

        if self._is_frequent_operation(
            client_id,
            audit_log,
            current_time,
        ):
            reasons.append("frequent_operations")

        if self._is_new_recipient(
            transaction,
            client_id,
            audit_log,
            current_time,
        ):
            reasons.append("new_recipient")

        if 0 <= current_time.hour < 5:
            reasons.append("night_operation")

        return {
            "risk_level": self._get_risk_level(len(reasons)),
            "reasons": reasons,
        }

    def _is_frequent_operation(
        self,
        client_id: str,
        audit_log: AuditLog,
        current_time: datetime,
    ) -> bool:
        start_time = (
            current_time - self._frequent_operations_window
        )
        recent_operations = audit_log.filter(
            event_type="transaction_requested",
            client_id=client_id,
            start_time=start_time,
            end_time=current_time,
        )
        return (
            len(recent_operations)
            >= self._frequent_operations_limit
        )

    @staticmethod
    def _is_new_recipient(
        transaction: Transaction,
        client_id: str,
        audit_log: AuditLog,
        current_time: datetime,
    ) -> bool:
        completed_operations = audit_log.filter(
            event_type="transaction_completed",
            client_id=client_id,
            end_time=current_time,
        )
        recipient_account_id = transaction.recipient.account_id

        for entry in completed_operations:
            details = entry["details"]
            if (
                isinstance(details, dict)
                and details.get("recipient_account_id")
                == recipient_account_id
            ):
                return False

        return True

    @staticmethod
    def _get_risk_level(reason_count: int) -> RiskLevel:
        if reason_count == 0:
            return RiskLevel.LOW
        if reason_count == 1:
            return RiskLevel.MEDIUM
        return RiskLevel.HIGH

    def _get_current_time(self) -> datetime:
        current_time = self._time_provider()
        if not isinstance(current_time, datetime):
            raise InvalidOperationError(
                "Источник времени должен возвращать datetime."
            )
        return current_time

    @staticmethod
    def _validate_transaction(
        transaction: Transaction,
    ) -> Transaction:
        if not isinstance(transaction, Transaction):
            raise InvalidOperationError(
                "Для анализа должна быть передана транзакция."
            )
        return transaction

    @staticmethod
    def _validate_client_id(client_id: str) -> str:
        if not isinstance(client_id, str) or not client_id.strip():
            raise InvalidOperationError(
                "ID клиента указан некорректно."
            )
        return client_id.strip()

    @staticmethod
    def _validate_audit_log(audit_log: AuditLog) -> AuditLog:
        if not isinstance(audit_log, AuditLog):
            raise InvalidOperationError(
                "Передан некорректный журнал аудита."
            )
        return audit_log

    @staticmethod
    def _validate_large_amount_threshold(
        threshold: Decimal | int | float | str,
    ) -> Decimal:
        if isinstance(threshold, bool):
            raise InvalidOperationError(
                "Лимит крупной суммы должен быть числом."
            )
        try:
            converted_threshold = Decimal(str(threshold))
        except (
            DecimalInvalidOperation,
            TypeError,
            ValueError,
        ) as error:
            raise InvalidOperationError(
                "Лимит крупной суммы должен быть числом."
            ) from error

        if (
            not converted_threshold.is_finite()
            or converted_threshold <= 0
        ):
            raise InvalidOperationError(
                "Лимит крупной суммы должен быть больше нуля."
            )
        return converted_threshold

    @staticmethod
    def _validate_frequent_operations_limit(
        limit: int,
    ) -> int:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit <= 0
        ):
            raise InvalidOperationError(
                "Лимит частых операций должен быть "
                "положительным целым числом."
            )
        return limit

    @staticmethod
    def _validate_frequent_operations_window(
        window: timedelta,
    ) -> timedelta:
        if (
            not isinstance(window, timedelta)
            or window <= timedelta(0)
        ):
            raise InvalidOperationError(
                "Интервал частых операций должен быть "
                "положительным."
            )
        return window
