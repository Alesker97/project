from src.demo.demo_builder import (
    DEMO_START_TIME,
    DEMO_TRANSACTION_GROUPS,
    MutableClock,
    create_demo_accounts,
    create_demo_bank,
    create_demo_clients,
    create_demo_processor,
    create_demo_queue,
    create_demo_transactions,
    register_demo_accounts,
)
from src.demo.demo_scenarios import (
    DEMO_CANCELLATION_REASON,
    add_transactions_to_queue,
    cancel_demo_transactions,
    get_demo_priority,
    prepare_demo_queue,
    run_transaction_simulation,
)
from src.enums.account_status import AccountStatus
from src.enums.transaction_priority import TransactionPriority
from src.enums.transaction_status import TransactionStatus


def test_demo_priorities_cover_all_transactions() -> None:
    clients = create_demo_clients()
    accounts = create_demo_accounts(clients)
    transactions = create_demo_transactions(accounts)

    priorities = [
        get_demo_priority(transaction.transaction_id)
        for transaction in transactions
    ]

    high_count = sum(
        priority is TransactionPriority.HIGH
        for priority in priorities
    )
    normal_count = sum(
        priority is TransactionPriority.NORMAL
        for priority in priorities
    )
    low_count = sum(
        priority is TransactionPriority.LOW
        for priority in priorities
    )

    assert high_count == 7
    assert normal_count == 17
    assert low_count == 16


def test_add_transactions_to_queue_adds_all_transactions(
) -> None:
    clock = MutableClock(DEMO_START_TIME)
    clients = create_demo_clients()
    accounts = create_demo_accounts(clients)
    transactions = create_demo_transactions(accounts)
    queue = create_demo_queue(clock)

    queue_log = add_transactions_to_queue(
        queue,
        transactions,
    )

    assert len(queue) == 40
    assert len(queue_log) == 40

    for entry in queue_log:
        assert entry["event_type"] == "transaction_queued"
        assert entry["transaction_id"]
        assert entry["priority"] in {
            TransactionPriority.HIGH.value,
            TransactionPriority.NORMAL.value,
            TransactionPriority.LOW.value,
        }


def test_adding_to_queue_does_not_process_transactions(
) -> None:
    clock = MutableClock(DEMO_START_TIME)
    clients = create_demo_clients()
    accounts = create_demo_accounts(clients)
    transactions = create_demo_transactions(accounts)
    queue = create_demo_queue(clock)

    add_transactions_to_queue(
        queue,
        transactions,
    )

    for transaction in transactions:
        assert transaction.status is TransactionStatus.PENDING
        assert transaction.attempts == 0


def test_cancel_demo_transactions_cancels_four_transactions(
) -> None:
    clock = MutableClock(DEMO_START_TIME)
    clients = create_demo_clients()
    accounts = create_demo_accounts(clients)
    transactions = create_demo_transactions(accounts)
    queue = create_demo_queue(clock)

    add_transactions_to_queue(
        queue,
        transactions,
    )
    cancellation_log = cancel_demo_transactions(
        queue,
        transactions,
    )

    cancelled_ids = {
        transaction.transaction_id
        for transaction in transactions
        if transaction.status is TransactionStatus.CANCELLED
    }

    assert cancelled_ids == set(
        DEMO_TRANSACTION_GROUPS["cancelled"]
    )
    assert len(cancellation_log) == 4

    for transaction in transactions:
        if transaction.transaction_id in cancelled_ids:
            assert (
                transaction.failure_reason
                == DEMO_CANCELLATION_REASON
            )
            assert transaction.attempts == 0
        else:
            assert transaction.status is TransactionStatus.PENDING


def test_prepare_demo_queue_creates_complete_queue_log(
) -> None:
    clock = MutableClock(DEMO_START_TIME)
    clients = create_demo_clients()
    accounts = create_demo_accounts(clients)
    transactions = create_demo_transactions(accounts)
    queue = create_demo_queue(clock)

    queue_log = prepare_demo_queue(
        queue,
        transactions,
    )

    queued_events = [
        entry
        for entry in queue_log
        if entry["event_type"] == "transaction_queued"
    ]
    cancelled_events = [
        entry
        for entry in queue_log
        if entry["event_type"] == "transaction_cancelled"
    ]

    assert len(queue_log) == 44
    assert len(queued_events) == 40
    assert len(cancelled_events) == 4


def test_transaction_simulation_processes_entire_queue(
) -> None:
    clock = MutableClock(DEMO_START_TIME)
    clients = create_demo_clients()
    bank, _, _ = create_demo_bank(clock, clients)
    accounts = create_demo_accounts(clients)
    register_demo_accounts(bank, clients, accounts)
    transactions = create_demo_transactions(accounts)
    queue = create_demo_queue(clock)
    processor = create_demo_processor(clock)

    prepare_demo_queue(queue, transactions)
    processing_log = run_transaction_simulation(
        clock,
        queue,
        bank,
        processor,
    )

    assert len(queue) == 0
    assert len(processing_log) == 36


def test_transaction_simulation_has_expected_results(
) -> None:
    clock = MutableClock(DEMO_START_TIME)
    clients = create_demo_clients()
    bank, _, _ = create_demo_bank(clock, clients)
    accounts = create_demo_accounts(clients)
    register_demo_accounts(bank, clients, accounts)
    transactions = create_demo_transactions(accounts)
    queue = create_demo_queue(clock)
    processor = create_demo_processor(clock)

    prepare_demo_queue(queue, transactions)
    processing_log = run_transaction_simulation(
        clock,
        queue,
        bank,
        processor,
    )

    completed_events = [
        entry
        for entry in processing_log
        if entry["event_type"] == "transaction_completed"
    ]
    failed_events = [
        entry
        for entry in processing_log
        if entry["event_type"] == "transaction_failed"
    ]
    blocked_events = [
        entry
        for entry in processing_log
        if entry["event_type"] == "transaction_blocked"
    ]

    assert len(completed_events) == 24
    assert len(failed_events) == 5
    assert len(blocked_events) == 7


def test_transaction_groups_have_expected_final_statuses(
) -> None:
    clock = MutableClock(DEMO_START_TIME)
    clients = create_demo_clients()
    bank, _, _ = create_demo_bank(clock, clients)
    accounts = create_demo_accounts(clients)
    register_demo_accounts(bank, clients, accounts)
    transactions = create_demo_transactions(accounts)
    queue = create_demo_queue(clock)
    processor = create_demo_processor(clock)

    prepare_demo_queue(queue, transactions)
    run_transaction_simulation(
        clock,
        queue,
        bank,
        processor,
    )

    transactions_by_id = {
        transaction.transaction_id: transaction
        for transaction in transactions
    }

    for transaction_id in DEMO_TRANSACTION_GROUPS["completed"]:
        transaction = transactions_by_id[transaction_id]

        assert transaction.status is TransactionStatus.COMPLETED
        assert transaction.attempts == 1

    for transaction_id in DEMO_TRANSACTION_GROUPS["failed"]:
        transaction = transactions_by_id[transaction_id]

        assert transaction.status is TransactionStatus.FAILED
        assert transaction.attempts == 1
        assert transaction.failure_reason is not None

    for transaction_id in DEMO_TRANSACTION_GROUPS["suspicious"]:
        transaction = transactions_by_id[transaction_id]

        assert transaction.status is TransactionStatus.FAILED
        assert transaction.attempts == 0
        assert transaction.failure_reason is not None

    for transaction_id in DEMO_TRANSACTION_GROUPS["cancelled"]:
        transaction = transactions_by_id[transaction_id]

        assert transaction.status is TransactionStatus.CANCELLED
        assert transaction.attempts == 0


def test_special_account_statuses_are_restored_after_processing(
) -> None:
    clock = MutableClock(DEMO_START_TIME)
    clients = create_demo_clients()
    bank, _, _ = create_demo_bank(clock, clients)
    accounts = create_demo_accounts(clients)
    register_demo_accounts(bank, clients, accounts)
    transactions = create_demo_transactions(accounts)
    queue = create_demo_queue(clock)
    processor = create_demo_processor(clock)

    prepare_demo_queue(queue, transactions)
    run_transaction_simulation(
        clock,
        queue,
        bank,
        processor,
    )

    assert (
        accounts["ivan_investment"].status
        is AccountStatus.ACTIVE
    )
    assert (
        accounts["alexey_checking"].status
        is AccountStatus.ACTIVE
    )


def test_high_priority_transactions_are_processed_first(
) -> None:
    clock = MutableClock(DEMO_START_TIME)
    clients = create_demo_clients()
    bank, _, _ = create_demo_bank(clock, clients)
    accounts = create_demo_accounts(clients)
    register_demo_accounts(bank, clients, accounts)
    transactions = create_demo_transactions(accounts)
    queue = create_demo_queue(clock)
    processor = create_demo_processor(clock)

    prepare_demo_queue(queue, transactions)
    processing_log = run_transaction_simulation(
        clock,
        queue,
        bank,
        processor,
    )

    first_transaction_ids = [
        entry["transaction_id"]
        for entry in processing_log[:7]
    ]

    assert first_transaction_ids == [
        "demo-tx-001",
        "demo-tx-005",
        "demo-tx-009",
        "demo-tx-013",
        "demo-tx-017",
        "demo-tx-023",
        "demo-tx-024",
    ]


def test_processing_log_contains_balance_snapshots(
) -> None:
    clock = MutableClock(DEMO_START_TIME)
    clients = create_demo_clients()
    bank, _, _ = create_demo_bank(clock, clients)
    accounts = create_demo_accounts(clients)
    register_demo_accounts(bank, clients, accounts)
    transactions = create_demo_transactions(accounts)
    queue = create_demo_queue(clock)
    processor = create_demo_processor(clock)

    prepare_demo_queue(queue, transactions)
    processing_log = run_transaction_simulation(
        clock,
        queue,
        bank,
        processor,
    )

    first_entry = processing_log[0]
    first_transaction = transactions[0]
    
    assert first_entry["status"] == (
        TransactionStatus.COMPLETED.value
    )

    assert first_entry["sender_account_id"] == (
        first_transaction.sender.account_id
    )
    assert first_entry["recipient_account_id"] == (
        first_transaction.recipient.account_id
    )
    assert (
        first_entry["sender_balance_after"]
        < first_entry["sender_balance_before"]
    )
    assert (
        first_entry["recipient_balance_after"]
        > first_entry["recipient_balance_before"]
    )
    assert first_entry["processed_at"] == DEMO_START_TIME
