from decimal import Decimal

from src.accounts.account_base import AbstractAccount
from src.audit.audit_report import AuditReport
from src.banks.bank import Bank
from src.clients.client import Client
from src.demo.demo_builder import (
    DEMO_START_TIME,
    MutableClock,
    create_demo_accounts,
    create_demo_bank,
    create_demo_clients,
    create_demo_processor,
    create_demo_queue,
    create_demo_transactions,
    register_demo_accounts,
)
from src.demo.demo_report import (
    display_client_accounts,
    display_client_history,
    display_client_risk_profile,
    display_error_statistics,
    display_processing_log,
    display_queue_log,
    display_suspicious_operations,
    display_top_clients,
    display_total_balance,
    display_transaction_statistics,
    get_client_accounts,
    get_client_history,
    get_client_risk_profile,
    get_client_suspicious_operations,
    get_error_statistics,
    get_suspicious_operations,
    get_top_clients,
    get_total_balance,
    get_transaction_statistics,
)
from src.demo.demo_scenarios import (
    prepare_demo_queue,
    run_transaction_simulation,
)
from src.enums.currency import Currency
from src.enums.transaction_status import TransactionStatus
from src.transactions.transaction import Transaction


def create_completed_simulation() -> tuple[
    Bank,
    dict[str, Client],
    dict[str, AbstractAccount],
    list[Transaction],
    AuditReport,
]:
    clock = MutableClock(DEMO_START_TIME)
    clients = create_demo_clients()
    bank, audit_log, _ = create_demo_bank(
        clock,
        clients,
    )
    accounts = create_demo_accounts(clients)
    register_demo_accounts(
        bank,
        clients,
        accounts,
    )
    transactions = create_demo_transactions(accounts)
    queue = create_demo_queue(clock)
    processor = create_demo_processor(clock)

    prepare_demo_queue(
        queue,
        transactions,
    )
    run_transaction_simulation(
        clock,
        queue,
        bank,
        processor,
    )

    return (
        bank,
        clients,
        accounts,
        transactions,
        AuditReport(audit_log),
    )


def test_get_client_accounts_returns_two_accounts() -> None:
    bank, clients, _, _, _ = create_completed_simulation()

    accounts = get_client_accounts(
        bank,
        clients["alexey"],
    )

    assert len(accounts) == 2
    assert {
        account.account_id
        for account in accounts
    } == set(clients["alexey"].account_ids)


def test_get_client_history_contains_incoming_and_outgoing(
) -> None:
    _, clients, _, transactions, _ = (
        create_completed_simulation()
    )

    history = get_client_history(
        clients["alexey"],
        transactions,
    )
    directions = {
        entry["direction"]
        for entry in history
    }

    assert history
    assert "incoming" in directions
    assert "outgoing" in directions

    for entry in history:
        assert entry["transaction_id"]
        assert entry["status"] in TransactionStatus
        assert entry["amount"] > Decimal("0")


def test_get_suspicious_operations_returns_risk_entries(
) -> None:
    _, _, _, _, audit_report = create_completed_simulation()

    suspicious_operations = get_suspicious_operations(
        audit_report
    )

    assert suspicious_operations

    for entry in suspicious_operations:
        assert entry["transaction_id"]
        assert entry["client_id"]
        assert "details" in entry


def test_get_client_suspicious_operations_filters_client(
) -> None:
    _, clients, _, _, audit_report = (
        create_completed_simulation()
    )

    suspicious_operations = (
        get_client_suspicious_operations(
            audit_report,
            clients["alexey"],
        )
    )

    assert suspicious_operations

    for entry in suspicious_operations:
        assert (
            entry["client_id"]
            == clients["alexey"].client_id
        )


def test_get_client_risk_profile_returns_client_data(
) -> None:
    _, clients, _, _, audit_report = (
        create_completed_simulation()
    )

    profile = get_client_risk_profile(
        audit_report,
        clients["alexey"],
    )

    assert profile["client_id"] == clients["alexey"].client_id
    assert profile["total_operations"] > 0
    assert "risk_counts" in profile
    assert "blocked_operations" in profile
    assert "maximum_risk" in profile


def test_get_error_statistics_returns_error_data() -> None:
    _, _, _, _, audit_report = create_completed_simulation()

    statistics = get_error_statistics(audit_report)

    assert statistics["total_errors"] > 0
    assert "by_event_type" in statistics
    assert "transaction_failed" in statistics["by_event_type"]
    assert "transaction_blocked" in statistics["by_event_type"]


def test_get_top_clients_returns_three_sorted_clients(
) -> None:
    bank, _, _, _, _ = create_completed_simulation()

    ranking = get_top_clients(
        bank,
        Currency.RUB,
    )

    assert len(ranking) == 3
    assert [
        entry["position"]
        for entry in ranking
    ] == [1, 2, 3]
    assert ranking[0]["balance"] >= ranking[1]["balance"]
    assert ranking[1]["balance"] >= ranking[2]["balance"]

    for entry in ranking:
        assert entry["currency"] is Currency.RUB


def test_get_transaction_statistics_returns_expected_counts(
) -> None:
    _, _, _, transactions, _ = create_completed_simulation()

    statistics = get_transaction_statistics(transactions)

    assert statistics["total"] == 40
    assert statistics["completed"] == 24
    assert statistics["failed"] == 12
    assert statistics["cancelled"] == 4
    assert statistics["blocked"] == 7
    assert statistics["processing_failures"] == 5
    assert statistics["by_status"]["pending"] == 0
    assert statistics["by_status"]["processing"] == 0
    assert statistics["by_status"]["completed"] == 24
    assert statistics["by_status"]["failed"] == 12
    assert statistics["by_status"]["cancelled"] == 4


def test_get_transaction_statistics_returns_commissions(
) -> None:
    _, _, _, transactions, _ = create_completed_simulation()

    statistics = get_transaction_statistics(transactions)
    commission_totals = statistics["commission_totals"]

    assert set(commission_totals) == {
        "RUB",
        "USD",
        "EUR",
        "KZT",
        "CNY",
    }
    assert commission_totals["RUB"] > Decimal("0")
    assert commission_totals["USD"] == Decimal("0")
    assert commission_totals["EUR"] == Decimal("0")
    assert commission_totals["KZT"] == Decimal("0")
    assert commission_totals["CNY"] == Decimal("0")


def test_get_total_balance_returns_every_currency() -> None:
    bank, _, _, _, _ = create_completed_simulation()

    total_balance = get_total_balance(bank)

    assert set(total_balance) == {
        "RUB",
        "USD",
        "EUR",
        "KZT",
        "CNY",
    }

    for balance in total_balance.values():
        assert isinstance(balance, Decimal)


def test_display_queue_log_prints_queued_and_cancelled_events(
    capsys,
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

    display_queue_log(queue_log)

    output = capsys.readouterr().out

    assert "Попадание транзакций в очередь:" in output
    assert "demo-tx-001" in output
    assert "Приоритет: high" in output
    assert "demo-tx-037" in output
    assert "Отменена демонстрационным сценарием" in output


def test_display_processing_log_prints_processing_results(
    capsys,
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

    display_processing_log(processing_log)

    output = capsys.readouterr().out

    assert "Результат обработки очереди:" in output
    assert "исполнена" in output
    assert "отклонена процессором" in output
    assert "заблокирована банком" in output


def test_display_client_accounts_and_history(
    capsys,
) -> None:
    bank, clients, _, transactions, _ = (
        create_completed_simulation()
    )
    client = clients["alexey"]

    display_client_accounts(
        bank,
        client,
    )
    display_client_history(
        client,
        transactions,
    )

    output = capsys.readouterr().out

    assert "Счета клиента Алексей Иванов:" in output
    assert "demo-acc-0001"[-4:] in output
    assert "История клиента Алексей Иванов:" in output
    assert "Направление: исходящая" in output
    assert "Направление: входящая" in output


def test_display_audit_reports(
    capsys,
) -> None:
    _, clients, _, _, audit_report = (
        create_completed_simulation()
    )

    display_suspicious_operations(audit_report)
    display_client_risk_profile(
        audit_report,
        clients["alexey"],
    )
    display_error_statistics(audit_report)

    output = capsys.readouterr().out

    assert "Подозрительные операции:" in output
    assert "Риск-профиль клиента Алексей Иванов:" in output
    assert "Максимальный риск:" in output
    assert "Статистика ошибок аудита:" in output
    assert "transaction_blocked" in output


def test_display_final_reports(
    capsys,
) -> None:
    bank, _, _, transactions, _ = (
        create_completed_simulation()
    )

    display_top_clients(
        bank,
        Currency.RUB,
    )
    display_transaction_statistics(transactions)
    display_total_balance(bank)

    output = capsys.readouterr().out

    assert "Топ-3 клиентов в RUB:" in output
    assert "Статистика транзакций:" in output
    assert "Всего: 40" in output
    assert "Исполнено: 24" in output
    assert "Отклонено: 12" in output
    assert "Отменено: 4" in output
    assert "Заблокировано банком: 7" in output
    assert "Ошибок обработки: 5" in output
    assert "Общий баланс банка:" in output
    assert "RUB:" in output
    assert "USD:" in output
    assert "EUR:" in output
