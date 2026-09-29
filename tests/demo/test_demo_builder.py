from datetime import datetime
from decimal import Decimal

from src.accounts.bank_account import BankAccount
from src.accounts.investment_account import InvestmentAccount
from src.accounts.premium_account import PremiumAccount
from src.accounts.savings_account import SavingsAccount
from src.audit.audit_log import AuditLog
from src.banks.bank import Bank
from src.demo.demo_builder import (
    AUDIT_FILE_PATH,
    DEMO_ACCOUNT_OWNERS,
    DEMO_PASSWORDS,
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
from src.enums.account_status import AccountStatus
from src.enums.client_status import ClientStatus
from src.enums.currency import Currency
from src.enums.transaction_status import TransactionStatus
from src.enums.transaction_type import TransactionType
from src.risk.risk_analyzer import RiskAnalyzer
from src.transactions.transaction_processor import TransactionProcessor
from src.transactions.transaction_queue import TransactionQueue


def test_mutable_clock_returns_current_time() -> None:
    clock = MutableClock(DEMO_START_TIME)

    assert clock() == DEMO_START_TIME


def test_mutable_clock_allows_time_change() -> None:
    clock = MutableClock(DEMO_START_TIME)
    changed_time = datetime(2026, 9, 29, 14, 0)

    clock.current_time = changed_time

    assert clock() == changed_time


def test_create_demo_clients_creates_six_clients() -> None:
    clients = create_demo_clients()

    assert len(clients) == 6
    assert set(clients) == {
        "alexey",
        "maria",
        "ivan",
        "elena",
        "dmitry",
        "olga",
    }


def test_demo_clients_have_unique_ids() -> None:
    clients = create_demo_clients()

    client_ids = {
        client.client_id
        for client in clients.values()
    }

    assert len(client_ids) == len(clients)


def test_demo_clients_have_valid_data() -> None:
    clients = create_demo_clients()

    for client in clients.values():
        assert client.full_name
        assert client.age >= 18
        assert client.status is ClientStatus.ACTIVE
        assert "phone" in client.contacts
        assert "email" in client.contacts
        assert client.account_ids == []


def test_every_demo_client_has_password() -> None:
    clients = create_demo_clients()

    assert set(DEMO_PASSWORDS) == set(clients)

    for password in DEMO_PASSWORDS.values():
        assert password


def test_create_demo_bank_returns_required_objects() -> None:
    clock = MutableClock(DEMO_START_TIME)
    clients = create_demo_clients()

    bank, audit_log, risk_analyzer = create_demo_bank(
        clock,
        clients,
    )

    assert isinstance(bank, Bank)
    assert isinstance(audit_log, AuditLog)
    assert isinstance(risk_analyzer, RiskAnalyzer)
    assert bank.audit_log is audit_log
    assert audit_log.file_path == AUDIT_FILE_PATH


def test_create_demo_bank_registers_all_clients() -> None:
    clock = MutableClock(DEMO_START_TIME)
    clients = create_demo_clients()
    bank, _, _ = create_demo_bank(clock, clients)

    for client_key, client in clients.items():
        result = bank.authenticate_client(
            client.client_id,
            DEMO_PASSWORDS[client_key],
        )

        assert result is True


def test_create_demo_accounts_creates_twelve_accounts() -> None:
    clients = create_demo_clients()

    accounts = create_demo_accounts(clients)

    assert len(accounts) == 12
    assert set(accounts) == set(DEMO_ACCOUNT_OWNERS)


def test_demo_accounts_have_unique_ids() -> None:
    clients = create_demo_clients()
    accounts = create_demo_accounts(clients)

    account_ids = {
        account.account_id
        for account in accounts.values()
    }

    assert len(account_ids) == len(accounts)


def test_demo_accounts_have_expected_types() -> None:
    clients = create_demo_clients()
    accounts = create_demo_accounts(clients)

    bank_accounts = [
        account
        for account in accounts.values()
        if type(account) is BankAccount
    ]
    savings_accounts = [
        account
        for account in accounts.values()
        if isinstance(account, SavingsAccount)
    ]
    premium_accounts = [
        account
        for account in accounts.values()
        if isinstance(account, PremiumAccount)
    ]
    investment_accounts = [
        account
        for account in accounts.values()
        if isinstance(account, InvestmentAccount)
    ]

    assert len(bank_accounts) == 5
    assert len(savings_accounts) == 3
    assert len(premium_accounts) == 2
    assert len(investment_accounts) == 2


def test_demo_accounts_have_valid_initial_data() -> None:
    clients = create_demo_clients()
    accounts = create_demo_accounts(clients)

    for account_key, account in accounts.items():
        client_key = DEMO_ACCOUNT_OWNERS[account_key]
        client = clients[client_key]

        assert account.owner == client.full_name
        assert account.balance > Decimal("0")
        assert account.status is AccountStatus.ACTIVE


def test_register_demo_accounts_assigns_two_accounts_to_each_client(
) -> None:
    clock = MutableClock(DEMO_START_TIME)
    clients = create_demo_clients()
    bank, _, _ = create_demo_bank(clock, clients)
    accounts = create_demo_accounts(clients)

    register_demo_accounts(
        bank,
        clients,
        accounts,
    )

    for client in clients.values():
        registered_accounts = bank.search_accounts(
            client_id=client.client_id,
        )

        assert len(client.account_ids) == 2
        assert len(registered_accounts) == 2
        assert {
            account.account_id
            for account in registered_accounts
        } == set(client.account_ids)


def test_registered_accounts_have_expected_total_balances() -> None:
    clock = MutableClock(DEMO_START_TIME)
    clients = create_demo_clients()
    bank, _, _ = create_demo_bank(clock, clients)
    accounts = create_demo_accounts(clients)

    register_demo_accounts(
        bank,
        clients,
        accounts,
    )

    total_balance = bank.get_total_balance()

    assert total_balance[Currency.RUB] == Decimal("302000")
    assert total_balance[Currency.USD] == Decimal("27000")
    assert total_balance[Currency.EUR] == Decimal("5000")
    assert total_balance[Currency.KZT] == Decimal("0")
    assert total_balance[Currency.CNY] == Decimal("0")


def test_create_demo_queue_returns_empty_queue() -> None:
    clock = MutableClock(DEMO_START_TIME)

    queue = create_demo_queue(clock)

    assert isinstance(queue, TransactionQueue)
    assert len(queue) == 0


def test_create_demo_processor_returns_configured_processor() -> None:
    clock = MutableClock(DEMO_START_TIME)

    processor = create_demo_processor(clock)

    assert isinstance(processor, TransactionProcessor)
    assert processor.error_log == []


def test_create_demo_transactions_creates_forty_transactions(
) -> None:
    clients = create_demo_clients()
    accounts = create_demo_accounts(clients)

    transactions = create_demo_transactions(accounts)

    assert len(transactions) == 40


def test_demo_transactions_have_unique_ids() -> None:
    clients = create_demo_clients()
    accounts = create_demo_accounts(clients)
    transactions = create_demo_transactions(accounts)

    transaction_ids = {
        transaction.transaction_id
        for transaction in transactions
    }

    assert len(transaction_ids) == len(transactions)


def test_demo_transaction_groups_contain_all_transactions(
) -> None:
    clients = create_demo_clients()
    accounts = create_demo_accounts(clients)
    transactions = create_demo_transactions(accounts)

    transaction_ids = {
        transaction.transaction_id
        for transaction in transactions
    }
    grouped_ids = set().union(
        *DEMO_TRANSACTION_GROUPS.values()
    )

    assert len(DEMO_TRANSACTION_GROUPS["completed"]) == 24
    assert len(DEMO_TRANSACTION_GROUPS["failed"]) == 5
    assert len(DEMO_TRANSACTION_GROUPS["suspicious"]) == 7
    assert len(DEMO_TRANSACTION_GROUPS["cancelled"]) == 4
    assert grouped_ids == transaction_ids


def test_demo_transactions_have_valid_initial_data() -> None:
    clients = create_demo_clients()
    accounts = create_demo_accounts(clients)
    transactions = create_demo_transactions(accounts)

    for transaction in transactions:
        assert transaction.amount > Decimal("0")
        assert transaction.status is TransactionStatus.PENDING
        assert transaction.sender is not transaction.recipient
        assert transaction.currency is transaction.sender.currency


def test_demo_transactions_include_both_types() -> None:
    clients = create_demo_clients()
    accounts = create_demo_accounts(clients)
    transactions = create_demo_transactions(accounts)

    internal_count = sum(
        transaction.transaction_type
        is TransactionType.INTERNAL_TRANSFER
        for transaction in transactions
    )
    external_count = sum(
        transaction.transaction_type
        is TransactionType.EXTERNAL_TRANSFER
        for transaction in transactions
    )

    assert internal_count == 27
    assert external_count == 13


def test_demo_transactions_include_delayed_operations(
) -> None:
    clients = create_demo_clients()
    accounts = create_demo_accounts(clients)
    transactions = create_demo_transactions(accounts)

    delayed_ids = {
        transaction.transaction_id
        for transaction in transactions
        if transaction.scheduled_at > DEMO_START_TIME
    }

    assert delayed_ids == {
        "demo-tx-021",
        "demo-tx-022",
        "demo-tx-036",
    }
