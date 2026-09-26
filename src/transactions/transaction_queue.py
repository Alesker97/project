from collections.abc import Callable
from datetime import datetime

from src.enums.transaction_priority import TransactionPriority
from src.enums.transaction_status import TransactionStatus
from src.exceptions import InvalidOperationError
from src.transactions.transaction import Transaction


class TransactionQueue:
    def __init__(
        self,
        time_provider: Callable[[], datetime] | None = None,
    ) -> None:
        if time_provider is not None and not callable(time_provider):
            raise InvalidOperationError(
                "Источник времени должен быть вызываемым объектом."
            )
        self._time_provider = time_provider or datetime.now
        self._items: list[
            tuple[TransactionPriority, int, Transaction]
        ] = []
        self._transaction_ids: set[str] = set()
        self._sequence = 0

    def add(
        self,
        transaction: Transaction,
        priority: TransactionPriority = TransactionPriority.NORMAL,
    ) -> None:
        if not isinstance(transaction, Transaction):
            raise InvalidOperationError(
                "В очередь можно добавить только транзакцию."
            )
        if not isinstance(priority, TransactionPriority):
            raise InvalidOperationError(
                "Указан недопустимый приоритет транзакции."
            )
        if transaction.status is not TransactionStatus.PENDING:
            raise InvalidOperationError(
                "В очередь можно добавить только ожидающую транзакцию."
            )
        if transaction.transaction_id in self._transaction_ids:
            raise InvalidOperationError(
                "Транзакция уже была добавлена в очередь."
            )

        self._items.append(
            (priority, self._sequence, transaction)
        )
        self._transaction_ids.add(transaction.transaction_id)
        self._sequence += 1

    def get_next(self) -> Transaction | None:
        current_time = self._get_current_time()
        available_indexes = [
            index
            for index, (_, _, transaction) in enumerate(self._items)
            if transaction.scheduled_at <= current_time
        ]

        if not available_indexes:
            return None

        selected_index = max(
            available_indexes,
            key=lambda index: (
                self._items[index][0],
                -self._items[index][1],
            ),
        )
        _, _, transaction = self._items.pop(selected_index)
        return transaction

    def cancel(
        self,
        transaction_id: str,
        reason: str = "Транзакция отменена.",
    ) -> Transaction:
        transaction_id = self._validate_transaction_id(
            transaction_id
        )

        for index, (_, _, transaction) in enumerate(self._items):
            if transaction.transaction_id == transaction_id:
                self._items.pop(index)
                transaction._mark_cancelled(
                    reason,
                    self._get_current_time(),
                )
                return transaction

        raise InvalidOperationError(
            "Транзакция не найдена в очереди."
        )

    def __len__(self) -> int:
        return len(self._items)

    def _get_current_time(self) -> datetime:
        current_time = self._time_provider()
        if not isinstance(current_time, datetime):
            raise InvalidOperationError(
                "Источник времени должен возвращать datetime."
            )
        return current_time

    @staticmethod
    def _validate_transaction_id(transaction_id: str) -> str:
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
