from datetime import datetime
from decimal import Decimal
import pytest

from src.accounts.bank_account import BankAccount
from src.enums.currency import Currency
from src.enums.transaction_priority import TransactionPriority
from src.enums.transaction_status import TransactionStatus
from src.enums.transaction_type import TransactionType
from src.exceptions import InvalidOperationError
from src.transactions.transaction import Transaction
from src.transactions.transaction_queue import TransactionQueue


class MutableClock:
    def __init__(self, current_time: datetime) -> None:
        self.current_time = current_time

    def __call__(self) -> datetime:
        return self.current_time


def create_transaction(
    transaction_id: str,
    created_at: datetime,
    scheduled_at: datetime | None = None,
) -> Transaction:
    sender = BankAccount(
        owner="Отправитель",
        balance=Decimal("10000"),
        currency=Currency.RUB,
        account_id=f"{transaction_id}-sender",
    )
    recipient = BankAccount(
        owner="Получатель",
        balance=Decimal("5000"),
        currency=Currency.RUB,
        account_id=f"{transaction_id}-recipient",
    )

    return Transaction(
        transaction_type=TransactionType.INTERNAL_TRANSFER,
        amount=Decimal("100"),
        currency=Currency.RUB,
        sender=sender,
        recipient=recipient,
        transaction_id=transaction_id,
        created_at=created_at,
        scheduled_at=scheduled_at,
    )

def test_add_transaction() -> None:
    current_time = datetime(2026, 9, 26, 12, 0)
    transaction = create_transaction(
        "transaction-001",
        current_time,
    )
    queue = TransactionQueue(
        time_provider=lambda: current_time
    )

    queue.add(transaction)

    assert len(queue) == 1
    assert queue.get_next() is transaction
    assert len(queue) == 0

def test_process_transactions_by_priority() -> None:
    current_time = datetime(2026, 9, 26, 12, 0)
    low = create_transaction("low", current_time)
    normal = create_transaction("normal", current_time)
    high = create_transaction("high", current_time)
    queue = TransactionQueue(
        time_provider=lambda: current_time
    )

    queue.add(low, TransactionPriority.LOW)
    queue.add(normal, TransactionPriority.NORMAL)
    queue.add(high, TransactionPriority.HIGH)

    assert queue.get_next() is high
    assert queue.get_next() is normal
    assert queue.get_next() is low
    assert queue.get_next() is None

def test_preserve_addition_order_for_equal_priority() -> None:
    current_time = datetime(2026, 9, 26, 12, 0)
    first = create_transaction("first", current_time)
    second = create_transaction("second", current_time)
    third = create_transaction("third", current_time)
    queue = TransactionQueue(
        time_provider=lambda: current_time
    )

    queue.add(first, TransactionPriority.NORMAL)
    queue.add(second, TransactionPriority.NORMAL)
    queue.add(third, TransactionPriority.NORMAL)

    assert queue.get_next() is first
    assert queue.get_next() is second
    assert queue.get_next() is third

def test_skip_delayed_transaction() -> None:
    current_time = datetime(2026, 9, 26, 12, 0)
    clock = MutableClock(current_time)
    delayed = create_transaction(
        "delayed",
        created_at=current_time,
        scheduled_at=datetime(2026, 9, 26, 13, 0),
    )
    queue = TransactionQueue(time_provider=clock)

    queue.add(delayed, TransactionPriority.HIGH)

    assert queue.get_next() is None
    assert len(queue) == 1

    clock.current_time = datetime(2026, 9, 26, 13, 0)

    assert queue.get_next() is delayed
    assert len(queue) == 0

def test_process_available_transaction_before_delayed() -> None:
    current_time = datetime(2026, 9, 26, 12, 0)
    delayed = create_transaction(
        "delayed-high",
        created_at=current_time,
        scheduled_at=datetime(2026, 9, 26, 13, 0),
    )
    available = create_transaction(
        "available-normal",
        created_at=current_time,
    )
    queue = TransactionQueue(
        time_provider=lambda: current_time
    )

    queue.add(delayed, TransactionPriority.HIGH)
    queue.add(available, TransactionPriority.NORMAL)

    assert queue.get_next() is available
    assert queue.get_next() is None
    assert len(queue) == 1

def test_cancel_transaction() -> None:
    current_time = datetime(2026, 9, 26, 12, 0)
    transaction = create_transaction(
        "transaction-002",
        current_time,
    )
    queue = TransactionQueue(
        time_provider=lambda: current_time
    )
    queue.add(transaction)

    cancelled = queue.cancel(
        transaction.transaction_id,
        reason="Отменена клиентом.",
    )

    assert cancelled is transaction
    assert transaction.status is TransactionStatus.CANCELLED
    assert transaction.failure_reason == "Отменена клиентом."
    assert transaction.processed_at == current_time
    assert len(queue) == 0

def test_reject_duplicate_transaction() -> None:
    current_time = datetime(2026, 9, 26, 12, 0)
    first = create_transaction("duplicate", current_time)
    second = create_transaction("duplicate", current_time)
    queue = TransactionQueue(
        time_provider=lambda: current_time
    )

    queue.add(first)

    with pytest.raises(InvalidOperationError):
        queue.add(second)

def test_reject_invalid_priority() -> None:
    current_time = datetime(2026, 9, 26, 12, 0)
    transaction = create_transaction(
        "transaction-003",
        current_time,
    )
    queue = TransactionQueue(
        time_provider=lambda: current_time
    )

    with pytest.raises(InvalidOperationError):
        queue.add(transaction, priority=10)

def test_reject_invalid_queue_item() -> None:
    queue = TransactionQueue()

    with pytest.raises(InvalidOperationError):
        queue.add("incorrect")

def test_reject_missing_transaction_cancellation() -> None:
    queue = TransactionQueue()

    with pytest.raises(InvalidOperationError):
        queue.cancel("missing-transaction")

def test_reject_invalid_time_provider_result() -> None:
    current_time = datetime(2026, 9, 26, 12, 0)
    transaction = create_transaction(
        "transaction-004",
        current_time,
    )
    queue = TransactionQueue(
        time_provider=lambda: "incorrect"
    )
    queue.add(transaction)

    with pytest.raises(InvalidOperationError):
        queue.get_next()
