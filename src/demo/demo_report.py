from decimal import Decimal

from src.accounts.account_base import AbstractAccount
from src.audit.audit_report import AuditReport
from src.banks.bank import Bank
from src.clients.client import Client
from src.enums.currency import Currency
from src.enums.transaction_priority import TransactionPriority
from src.enums.transaction_status import TransactionStatus
from src.transactions.transaction import Transaction


def get_client_accounts(
    bank: Bank,
    client: Client,
) -> list[AbstractAccount]:
    return bank.search_accounts(
        client_id=client.client_id,
    )


def get_client_history(
    client: Client,
    transactions: list[Transaction],
) -> list[dict[str, object]]:
    account_ids = set(client.account_ids)
    history: list[dict[str, object]] = []

    for transaction in transactions:
        sender_account_id = transaction.sender.account_id
        recipient_account_id = transaction.recipient.account_id

        if (
            sender_account_id not in account_ids
            and recipient_account_id not in account_ids
        ):
            continue

        if (
            sender_account_id in account_ids
            and recipient_account_id in account_ids
        ):
            direction = "internal"
        elif sender_account_id in account_ids:
            direction = "outgoing"
        else:
            direction = "incoming"

        history.append(
            {
                "transaction_id": transaction.transaction_id,
                "direction": direction,
                "sender_account_id": sender_account_id,
                "recipient_account_id": recipient_account_id,
                "amount": transaction.amount,
                "currency": transaction.currency,
                "commission": transaction.commission,
                "status": transaction.status,
                "failure_reason": transaction.failure_reason,
                "attempts": transaction.attempts,
            }
        )

    return history


def get_suspicious_operations(
    audit_report: AuditReport,
) -> list[dict[str, object]]:
    return audit_report.get_suspicious_operations()


def get_client_suspicious_operations(
    audit_report: AuditReport,
    client: Client,
) -> list[dict[str, object]]:
    return [
        entry
        for entry in audit_report.get_suspicious_operations()
        if entry.get("client_id") == client.client_id
    ]


def get_client_risk_profile(
    audit_report: AuditReport,
    client: Client,
) -> dict[str, object]:
    return audit_report.get_client_risk_profile(
        client.client_id
    )


def get_error_statistics(
    audit_report: AuditReport,
) -> dict[str, object]:
    return audit_report.get_error_statistics()


def get_top_clients(
    bank: Bank,
    currency: Currency,
    limit: int = 3,
) -> list[dict[str, object]]:
    ranking = bank.get_clients_ranking(currency)

    return [
        {
            "position": position,
            "client_id": client.client_id,
            "full_name": client.full_name,
            "balance": balance,
            "currency": currency,
        }
        for position, (client, balance) in enumerate(
            ranking[:limit],
            start=1,
        )
    ]


def get_transaction_statistics(
    transactions: list[Transaction],
) -> dict[str, object]:
    status_counts = {
        status.value: sum(
            transaction.status is status
            for transaction in transactions
        )
        for status in TransactionStatus
    }
    commission_totals = {
        currency.value: sum(
            (
                transaction.commission
                for transaction in transactions
                if transaction.currency is currency
            ),
            Decimal("0"),
        )
        for currency in Currency
    }
    blocked_count = sum(
        transaction.status is TransactionStatus.FAILED
        and transaction.attempts == 0
        for transaction in transactions
    )
    processing_failure_count = sum(
        transaction.status is TransactionStatus.FAILED
        and transaction.attempts > 0
        for transaction in transactions
    )

    return {
        "total": len(transactions),
        "by_status": status_counts,
        "completed": status_counts[
            TransactionStatus.COMPLETED.value
        ],
        "failed": status_counts[
            TransactionStatus.FAILED.value
        ],
        "cancelled": status_counts[
            TransactionStatus.CANCELLED.value
        ],
        "blocked": blocked_count,
        "processing_failures": processing_failure_count,
        "commission_totals": commission_totals,
    }


def get_total_balance(
    bank: Bank,
) -> dict[str, Decimal]:
    return {
        currency.value: balance
        for currency, balance
        in bank.get_total_balance().items()
    }


def display_queue_log(
    queue_log: list[dict[str, object]],
) -> None:
    print("\nПопадание транзакций в очередь:")

    for entry in queue_log:
        if entry["event_type"] == "transaction_queued":
            priority = TransactionPriority(
                entry["priority"]
            )

            print(
                f'{entry["transaction_id"]} | '
                f'Приоритет: {priority.name.lower()} | '
                f'Время выполнения: {entry["scheduled_at"]}'
            )
        else:
            print(
                f'{entry["transaction_id"]} | '
                f'Статус: {entry["status"]} | '
                f'Причина: {entry["reason"]}'
            )


def display_processing_log(
    processing_log: list[dict[str, object]],
) -> None:
    event_names = {
        "transaction_completed": "исполнена",
        "transaction_failed": "отклонена процессором",
        "transaction_blocked": "заблокирована банком",
    }

    print("\nРезультат обработки очереди:")

    for entry in processing_log:
        print(
            f'{entry["transaction_id"]} | '
            f'Результат: {event_names[entry["event_type"]]} | '
            f'Статус: {entry["status"]} | '
            f'Попытки: {entry["attempts"]}'
        )

        if entry["failure_reason"] is not None:
            print(f'Причина: {entry["failure_reason"]}')


def display_client_accounts(
    bank: Bank,
    client: Client,
) -> None:
    accounts = get_client_accounts(
        bank,
        client,
    )

    print(f"\nСчета клиента {client.full_name}:")

    for account in accounts:
        print(account)


def display_client_history(
    client: Client,
    transactions: list[Transaction],
) -> None:
    history = get_client_history(
        client,
        transactions,
    )
    direction_names = {
        "incoming": "входящая",
        "outgoing": "исходящая",
        "internal": "между своими счетами",
    }

    print(f"\nИстория клиента {client.full_name}:")

    if not history:
        print("Операции отсутствуют.")
        return

    for entry in history:
        print(
            f'{entry["transaction_id"]} | '
            f'Направление: '
            f'{direction_names[entry["direction"]]} | '
            f'Сумма: {entry["amount"]:.2f} '
            f'{entry["currency"].value} | '
            f'Статус: {entry["status"].value}'
        )

        if entry["failure_reason"] is not None:
            print(f'Причина: {entry["failure_reason"]}')


def display_suspicious_operations(
    audit_report: AuditReport,
) -> None:
    operations = get_suspicious_operations(
        audit_report
    )

    print("\nПодозрительные операции:")

    if not operations:
        print("Подозрительные операции отсутствуют.")
        return

    for entry in operations:
        details = entry["details"]
        risk_level = details["risk_level"]
        reasons = ", ".join(details["reasons"])

        print(
            f'{entry["transaction_id"]} | '
            f'Клиент: {entry["client_id"]} | '
            f'Риск: {risk_level.value} | '
            f'Причины: {reasons}'
        )


def display_client_risk_profile(
    audit_report: AuditReport,
    client: Client,
) -> None:
    profile = get_client_risk_profile(
        audit_report,
        client,
    )
    maximum_risk = profile["maximum_risk"]

    print(f"\nРиск-профиль клиента {client.full_name}:")
    print(
        f'Всего операций: {profile["total_operations"]}'
    )
    print(
        f'Заблокировано: '
        f'{profile["blocked_operations"]}'
    )
    print(
        f'Максимальный риск: {maximum_risk.value}'
    )

    for risk_level, count in profile["risk_counts"].items():
        print(f"{risk_level}: {count}")


def display_top_clients(
    bank: Bank,
    currency: Currency,
) -> None:
    ranking = get_top_clients(
        bank,
        currency,
    )

    print(f"\nТоп-3 клиентов в {currency.value}:")

    for entry in ranking:
        print(
            f'{entry["position"]}. '
            f'{entry["full_name"]}: '
            f'{entry["balance"]:.2f} '
            f'{entry["currency"].value}'
        )


def display_transaction_statistics(
    transactions: list[Transaction],
) -> None:
    statistics = get_transaction_statistics(
        transactions
    )

    print("\nСтатистика транзакций:")
    print(f'Всего: {statistics["total"]}')

    for status, count in statistics["by_status"].items():
        print(f"{status}: {count}")

    print(f'Исполнено: {statistics["completed"]}')
    print(f'Отклонено: {statistics["failed"]}')
    print(f'Отменено: {statistics["cancelled"]}')
    print(f'Заблокировано банком: {statistics["blocked"]}')
    print(
        f'Ошибок обработки: '
        f'{statistics["processing_failures"]}'
    )

    print("\nКомиссии:")

    for currency, amount in (
        statistics["commission_totals"].items()
    ):
        print(f"{currency}: {amount:.2f}")


def display_total_balance(
    bank: Bank,
) -> None:
    total_balance = get_total_balance(bank)

    print("\nОбщий баланс банка:")

    for currency, balance in total_balance.items():
        print(f"{currency}: {balance:.2f}")


def display_error_statistics(
    audit_report: AuditReport,
) -> None:
    statistics = get_error_statistics(audit_report)

    print("\nСтатистика ошибок аудита:")
    print(f'Всего ошибок: {statistics["total_errors"]}')

    for event_type, count in (
        statistics["by_event_type"].items()
    ):
        print(f"{event_type}: {count}")
