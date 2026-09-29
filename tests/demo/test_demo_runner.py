from src.demo.demo_runner import DemoRunner
from src.enums.transaction_status import TransactionStatus


def test_demo_runner_creates_required_objects() -> None:
    runner = DemoRunner()

    assert len(runner.clients) == 6
    assert len(runner.accounts) == 12
    assert len(runner.transactions) == 40
    assert len(runner.bank.search_accounts()) == 12
    assert len(runner.queue) == 0
    assert runner.queue_log == []
    assert runner.processing_log == []


def test_demo_runner_executes_complete_simulation(
    capsys,
) -> None:
    runner = DemoRunner()

    runner.run()

    output = capsys.readouterr().out

    assert len(runner.queue) == 0
    assert len(runner.queue_log) == 44
    assert len(runner.processing_log) == 36
    assert len(runner.audit_log) > 0

    assert "Комплексная демонстрация банковской системы" in output
    assert "Клиентов: 6" in output
    assert "Счетов: 12" in output
    assert "Транзакций: 40" in output
    assert "Попадание транзакций в очередь:" in output
    assert "Результат обработки очереди:" in output
    assert "Счета клиента Алексей Иванов:" in output
    assert "История клиента Алексей Иванов:" in output
    assert "Подозрительные операции:" in output
    assert "Риск-профиль клиента Алексей Иванов:" in output
    assert "Топ-3 клиентов в RUB:" in output
    assert "Статистика транзакций:" in output
    assert "Общий баланс банка:" in output
    assert "Статистика ошибок аудита:" in output
    assert "Подозрительные действия банка:" in output
    assert "Файл аудита:" in output
    assert "audit.jsonl" in output


def test_demo_runner_produces_expected_statuses() -> None:
    runner = DemoRunner()

    runner.run()

    completed_count = sum(
        transaction.status is TransactionStatus.COMPLETED
        for transaction in runner.transactions
    )
    failed_count = sum(
        transaction.status is TransactionStatus.FAILED
        for transaction in runner.transactions
    )
    cancelled_count = sum(
        transaction.status is TransactionStatus.CANCELLED
        for transaction in runner.transactions
    )

    assert completed_count == 24
    assert failed_count == 12
    assert cancelled_count == 4


def test_demo_runner_produces_expected_processing_results(
) -> None:
    runner = DemoRunner()

    runner.run()

    completed_count = sum(
        entry["event_type"] == "transaction_completed"
        for entry in runner.processing_log
    )
    failed_count = sum(
        entry["event_type"] == "transaction_failed"
        for entry in runner.processing_log
    )
    blocked_count = sum(
        entry["event_type"] == "transaction_blocked"
        for entry in runner.processing_log
    )

    assert completed_count == 24
    assert failed_count == 5
    assert blocked_count == 7
