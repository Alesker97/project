from src.banks.bank import Bank
from src.demo.demo_builder import (
    DEMO_DELAYED_TIME,
    DEMO_NIGHT_TIME,
    DEMO_START_TIME,
    DEMO_TRANSACTION_GROUPS,
    MutableClock,
)
from src.enums.transaction_priority import TransactionPriority
from src.transactions.transaction import Transaction
from src.transactions.transaction_processor import TransactionProcessor
from src.transactions.transaction_queue import TransactionQueue


DEMO_HIGH_PRIORITY_IDS = frozenset(
    {
        "demo-tx-001",
        "demo-tx-005",
        "demo-tx-009",
        "demo-tx-013",
        "demo-tx-017",
        "demo-tx-023",
        "demo-tx-024",
    }
)

DEMO_LOW_PRIORITY_IDS = frozenset(
    f"demo-tx-{number:03d}"
    for number in range(25, 41)
)

DEMO_CANCELLATION_REASON = (
    "Отменена демонстрационным сценарием до обработки."
)


def get_demo_priority(
    transaction_id: str,
) -> TransactionPriority:
    if transaction_id in DEMO_HIGH_PRIORITY_IDS:
        return TransactionPriority.HIGH

    if transaction_id in DEMO_LOW_PRIORITY_IDS:
        return TransactionPriority.LOW

    return TransactionPriority.NORMAL


def add_transactions_to_queue(
    queue: TransactionQueue,
    transactions: list[Transaction],
) -> list[dict[str, object]]:
    queue_log: list[dict[str, object]] = []

    for transaction in transactions:
        priority = get_demo_priority(
            transaction.transaction_id
        )
        queue.add(transaction, priority)
        queue_log.append(
            {
                "event_type": "transaction_queued",
                "transaction_id": transaction.transaction_id,
                "priority": priority.value,
                "scheduled_at": transaction.scheduled_at,
            }
        )

    return queue_log


def cancel_demo_transactions(
    queue: TransactionQueue,
    transactions: list[Transaction],
) -> list[dict[str, object]]:
    transactions_by_id = {
        transaction.transaction_id: transaction
        for transaction in transactions
    }
    cancellation_log: list[dict[str, object]] = []

    for transaction_id in sorted(
        DEMO_TRANSACTION_GROUPS["cancelled"]
    ):
        queue.cancel(
            transaction_id,
            reason=DEMO_CANCELLATION_REASON,
        )
        transaction = transactions_by_id[transaction_id]
        cancellation_log.append(
            {
                "event_type": "transaction_cancelled",
                "transaction_id": transaction_id,
                "status": transaction.status.value,
                "reason": transaction.failure_reason,
            }
        )

    return cancellation_log


def prepare_demo_queue(
    queue: TransactionQueue,
    transactions: list[Transaction],
) -> list[dict[str, object]]:
    queue_log = add_transactions_to_queue(
        queue,
        transactions,
    )
    queue_log.extend(
        cancel_demo_transactions(
            queue,
            transactions,
        )
    )

    return queue_log


def get_processing_event_type(
    transaction: Transaction,
    result: bool,
) -> str:
    if result:
        return "transaction_completed"

    if transaction.attempts == 0:
        return "transaction_blocked"

    return "transaction_failed"


def prepare_account_status(
    bank: Bank,
    transaction: Transaction,
) -> str | None:
    account_id = None

    if transaction.transaction_id == "demo-tx-026":
        account_id = transaction.sender.account_id

    if transaction.transaction_id == "demo-tx-029":
        account_id = transaction.recipient.account_id

    if account_id is not None:
        bank.freeze_account(account_id)

    return account_id


def restore_account_status(
    bank: Bank,
    account_id: str | None,
) -> None:
    if account_id is not None:
        bank.unfreeze_account(account_id)


def process_available_transactions(
    queue: TransactionQueue,
    bank: Bank,
    processor: TransactionProcessor,
) -> list[dict[str, object]]:
    processing_log: list[dict[str, object]] = []

    while True:
        transaction = queue.get_next()

        if transaction is None:
            break

        frozen_account_id = prepare_account_status(
            bank,
            transaction,
        )

        try:
            result = bank.process_transaction(
                transaction,
                processor,
            )
        finally:
            restore_account_status(
                bank,
                frozen_account_id,
            )

        processing_log.append(
            {
                "event_type": get_processing_event_type(
                    transaction,
                    result,
                ),
                "transaction_id": transaction.transaction_id,
                "status": transaction.status.value,
                "attempts": transaction.attempts,
                "failure_reason": transaction.failure_reason,
            }
        )

    return processing_log


def run_transaction_simulation(
    clock: MutableClock,
    queue: TransactionQueue,
    bank: Bank,
    processor: TransactionProcessor,
) -> list[dict[str, object]]:
    processing_log: list[dict[str, object]] = []

    clock.current_time = DEMO_START_TIME
    processing_log.extend(
        process_available_transactions(
            queue,
            bank,
            processor,
        )
    )

    clock.current_time = DEMO_DELAYED_TIME
    processing_log.extend(
        process_available_transactions(
            queue,
            bank,
            processor,
        )
    )

    clock.current_time = DEMO_NIGHT_TIME
    processing_log.extend(
        process_available_transactions(
            queue,
            bank,
            processor,
        )
    )

    return processing_log
