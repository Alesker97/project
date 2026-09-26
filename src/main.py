from datetime import datetime
from decimal import Decimal

from src.accounts.account_base import AbstractAccount
from src.accounts.bank_account import BankAccount
from src.accounts.investment_account import InvestmentAccount
from src.accounts.premium_account import PremiumAccount
from src.accounts.savings_account import SavingsAccount
from src.audit.audit_log import AuditLog
from src.audit.audit_report import AuditReport
from src.banks.bank import Bank
from src.clients.client import Client
from src.enums.asset_type import AssetType
from src.enums.currency import Currency
from src.enums.transaction_priority import TransactionPriority
from src.enums.transaction_status import TransactionStatus
from src.enums.transaction_type import TransactionType
from src.exceptions import InvalidOperationError
from src.risk.risk_analyzer import RiskAnalyzer
from src.transactions.transaction import Transaction
from src.transactions.transaction_processor import TransactionProcessor
from src.transactions.transaction_queue import TransactionQueue


class MutableClock:
    def __init__(self, current_time: datetime) -> None:
        self.current_time = current_time

    def __call__(self) -> datetime:
        return self.current_time


def create_demo_bank(
    clock: MutableClock,
) -> tuple[
    Bank,
    dict[str, Client],
    dict[str, AbstractAccount],
]:
    bank = Bank(time_provider=clock)

    clients = {
        "alexey": Client(
            full_name="Алексей Иванов",
            client_id="client-001",
            age=30,
            contacts={
                "phone": "+79990000001",
                "email": "alexey@example.com",
            },
        ),
        "maria": Client(
            full_name="Мария Петрова",
            client_id="client-002",
            age=28,
            contacts={
                "phone": "+79990000002",
                "email": "maria@example.com",
            },
        ),
        "ivan": Client(
            full_name="Иван Сидоров",
            client_id="client-003",
            age=35,
            contacts={
                "phone": "+79990000003",
                "email": "ivan@example.com",
            },
        ),
    }

    bank.add_client(clients["alexey"], "alexey-password")
    bank.add_client(clients["maria"], "maria-password")
    bank.add_client(clients["ivan"], "ivan-password")

    accounts: dict[str, AbstractAccount] = {
        "savings": SavingsAccount(
            owner=clients["alexey"].full_name,
            balance=Decimal("10000"),
            currency=Currency.RUB,
            min_balance=Decimal("1000"),
            monthly_interest_rate=Decimal("0.01"),
            account_id="savings-001",
        ),
        "premium": PremiumAccount(
            owner=clients["maria"].full_name,
            balance=Decimal("5000"),
            currency=Currency.RUB,
            withdrawal_limit=Decimal("50000"),
            overdraft_limit=Decimal("5000"),
            fixed_commission=Decimal("100"),
            account_id="premium-001",
        ),
        "investment": InvestmentAccount(
            owner=clients["ivan"].full_name,
            balance=Decimal("30000"),
            currency=Currency.USD,
            account_id="investment-001",
        ),
        "reserve": BankAccount(
            owner=clients["alexey"].full_name,
            balance=Decimal("1000"),
            currency=Currency.RUB,
            account_id="reserve-001",
        ),
    }

    bank.open_account(
        clients["alexey"].client_id,
        accounts["savings"],
    )
    bank.open_account(
        clients["maria"].client_id,
        accounts["premium"],
    )
    bank.open_account(
        clients["ivan"].client_id,
        accounts["investment"],
    )
    bank.open_account(
        clients["alexey"].client_id,
        accounts["reserve"],
    )

    savings = accounts["savings"]
    investment = accounts["investment"]

    if isinstance(savings, SavingsAccount):
        savings.apply_monthly_interest()

    if isinstance(investment, InvestmentAccount):
        investment.invest(
            AssetType.STOCKS,
            Decimal("10000"),
        )
        investment.invest(
            AssetType.BONDS,
            Decimal("5000"),
        )
        investment.invest(
            AssetType.ETF,
            Decimal("5000"),
        )

    return bank, clients, accounts

def create_transactions(
    accounts: dict[str, AbstractAccount],
    created_at: datetime,
) -> list[Transaction]:
    return [
        Transaction(
            transaction_type=TransactionType.INTERNAL_TRANSFER,
            amount=Decimal("500"),
            currency=Currency.RUB,
            sender=accounts["savings"],
            recipient=accounts["premium"],
            transaction_id="transaction-001",
            created_at=created_at,
        ),
        Transaction(
            transaction_type=TransactionType.EXTERNAL_TRANSFER,
            amount=Decimal("200"),
            currency=Currency.RUB,
            sender=accounts["premium"],
            recipient=accounts["savings"],
            transaction_id="transaction-002",
            created_at=created_at,
        ),
        Transaction(
            transaction_type=TransactionType.INTERNAL_TRANSFER,
            amount=Decimal("10"),
            currency=Currency.USD,
            sender=accounts["investment"],
            recipient=accounts["savings"],
            transaction_id="transaction-003",
            created_at=created_at,
        ),
        Transaction(
            transaction_type=TransactionType.INTERNAL_TRANSFER,
            amount=Decimal("800"),
            currency=Currency.RUB,
            sender=accounts["savings"],
            recipient=accounts["investment"],
            transaction_id="transaction-004",
            created_at=created_at,
        ),
        Transaction(
            transaction_type=TransactionType.INTERNAL_TRANSFER,
            amount=Decimal("5500"),
            currency=Currency.RUB,
            sender=accounts["premium"],
            recipient=accounts["savings"],
            transaction_id="transaction-005",
            created_at=created_at,
        ),
        Transaction(
            transaction_type=TransactionType.INTERNAL_TRANSFER,
            amount=Decimal("100"),
            currency=Currency.RUB,
            sender=accounts["reserve"],
            recipient=accounts["savings"],
            transaction_id="transaction-006",
            created_at=created_at,
        ),
        Transaction(
            transaction_type=TransactionType.INTERNAL_TRANSFER,
            amount=Decimal("100"),
            currency=Currency.RUB,
            sender=accounts["savings"],
            recipient=accounts["reserve"],
            transaction_id="transaction-007",
            created_at=created_at,
        ),
        Transaction(
            transaction_type=TransactionType.INTERNAL_TRANSFER,
            amount=Decimal("100000"),
            currency=Currency.RUB,
            sender=accounts["savings"],
            recipient=accounts["investment"],
            transaction_id="transaction-008",
            created_at=created_at,
        ),
        Transaction(
            transaction_type=TransactionType.INTERNAL_TRANSFER,
            amount=Decimal("100"),
            currency=Currency.RUB,
            sender=accounts["savings"],
            recipient=accounts["premium"],
            transaction_id="transaction-009",
            created_at=created_at,
            scheduled_at=datetime(2026, 9, 26, 13, 0),
        ),
        Transaction(
            transaction_type=TransactionType.INTERNAL_TRANSFER,
            amount=Decimal("50"),
            currency=Currency.RUB,
            sender=accounts["savings"],
            recipient=accounts["premium"],
            transaction_id="transaction-010",
            created_at=created_at,
        ),
    ]

def prepare_transaction_queue(
    transactions: list[Transaction],
    clock: MutableClock,
) -> TransactionQueue:
    priorities = [
        TransactionPriority.HIGH,
        TransactionPriority.HIGH,
        TransactionPriority.NORMAL,
        TransactionPriority.NORMAL,
        TransactionPriority.NORMAL,
        TransactionPriority.LOW,
        TransactionPriority.LOW,
        TransactionPriority.LOW,
        TransactionPriority.HIGH,
        TransactionPriority.NORMAL,
    ]
    queue = TransactionQueue(time_provider=clock)

    for transaction, priority in zip(
        transactions,
        priorities,
        strict=True,
    ):
        queue.add(transaction, priority)

    queue.cancel(
        "transaction-010",
        reason="Отменена до начала обработки.",
    )
    return queue

def process_transactions(
    queue: TransactionQueue,
    clock: MutableClock,
) -> tuple[TransactionProcessor, list[Transaction]]:
    processor = TransactionProcessor(
        external_commission_rate=Decimal("0.01"),
        conversion_rates={
            (Currency.USD, Currency.RUB): Decimal("80"),
            (Currency.RUB, Currency.USD): Decimal("0.0125"),
        },
        max_retries=2,
        time_provider=clock,
    )

    processed_transactions = processor.process_all(queue)

    print("Осталось в очереди после первой обработки:", len(queue))

    clock.current_time = datetime(2026, 9, 26, 13, 0)
    processed_transactions.extend(
        processor.process_all(queue)
    )

    print("Осталось в очереди после изменения времени:", len(queue))
    return processor, processed_transactions

def display_processing_order(
    processed_transactions: list[Transaction],
) -> None:
    print("\nПорядок обработки:")

    for position, transaction in enumerate(
        processed_transactions,
        start=1,
    ):
        print(
            f"{position}. {transaction.transaction_id} — "
            f"{transaction.status.value}"
        )

def display_transactions(
    transactions: list[Transaction],
) -> None:
    print("\nИтоговые состояния транзакций:")

    for transaction in transactions:
        print(
            f"{transaction.transaction_id} | "
            f"Тип: {transaction.transaction_type.value} | "
            f"Сумма: {transaction.amount:.2f} "
            f"{transaction.currency.value} | "
            f"Комиссия: {transaction.commission:.2f} "
            f"{transaction.currency.value} | "
            f"Статус: {transaction.status.value} | "
            f"Попытки: {transaction.attempts}"
        )

        if transaction.failure_reason is not None:
            print(
                f"Причина: {transaction.failure_reason}"
            )

def display_transaction_summary(
    transactions: list[Transaction],
) -> None:
    summary = {
        status: sum(
            transaction.status is status
            for transaction in transactions
        )
        for status in TransactionStatus
    }

    print("\nРезультат обработки 10 транзакций:")

    for status, count in summary.items():
        print(f"{status.value}: {count}")

def display_error_log(
    processor: TransactionProcessor,
) -> None:
    print("\nОшибки обработки:")

    if not processor.error_log:
        print("Ошибок нет.")
        return

    for entry in processor.error_log:
        print(entry)

def demonstrate_authentication(
    bank: Bank,
    clients: dict[str, Client],
) -> None:
    alexey_result = bank.authenticate_client(
        clients["alexey"].client_id,
        "alexey-password",
    )
    print("\nУспешный вход Алексея:", alexey_result)

    for attempt in range(1, 4):
        result = bank.authenticate_client(
            clients["maria"].client_id,
            "incorrect-password",
        )
        print(
            f"Неудачный вход Марии №{attempt}: {result}"
        )

    print(
        "Статус Марии:",
        clients["maria"].status.value,
    )

def display_accounts(bank: Bank) -> None:
    print("\nИтоговое состояние счетов:")

    for account in bank.search_accounts():
        print(f"\n{account}")
        print(account.get_account_info())

def display_analytics(bank: Bank) -> None:
    print("\nОбщие балансы:")

    for currency, balance in bank.get_total_balance().items():
        print(f"{currency.value}: {balance:.2f}")

    print("\nРейтинг клиентов в RUB:")

    for position, (client, balance) in enumerate(
        bank.get_clients_ranking(Currency.RUB),
        start=1,
    ):
        print(
            f"{position}. {client.full_name}: "
            f"{balance:.2f} RUB"
        )

def display_suspicious_actions(bank: Bank) -> None:
    print("\nПодозрительные действия:")

    for action in bank.suspicious_actions:
        print(action)

def demonstrate_night_restriction() -> None:
    night_time = datetime(2026, 9, 26, 2, 0)
    night_bank = Bank(time_provider=lambda: night_time)
    client = Client(
        full_name="Ночной клиент",
        client_id="client-night",
        age=25,
        contacts={"phone": "+79990000004"},
    )
    account = BankAccount(
        owner=client.full_name,
        balance=Decimal("1000"),
        currency=Currency.RUB,
        account_id="night-001",
    )

    night_bank.add_client(client, "night-password")

    try:
        night_bank.open_account(
            client.client_id,
            account,
        )
    except InvalidOperationError as error:
        print(f"\nНочная операция отклонена: {error}")

    print(night_bank.suspicious_actions)

def create_audit_transaction(
    transaction_id: str,
    sender: AbstractAccount,
    recipient: AbstractAccount,
    amount: Decimal,
    created_at: datetime,
) -> Transaction:
    return Transaction(
        transaction_type=TransactionType.INTERNAL_TRANSFER,
        amount=amount,
        currency=sender.currency,
        sender=sender,
        recipient=recipient,
        transaction_id=transaction_id,
        created_at=created_at,
    )

def demonstrate_audit_and_risk() -> None:
    clock = MutableClock(
        datetime(2026, 9, 27, 12, 0)
    )
    audit_log = AuditLog(
        file_path="logs/audit.jsonl",
        time_provider=clock,
    )
    risk_analyzer = RiskAnalyzer(
        large_amount_threshold=Decimal("10000"),
        frequent_operations_limit=3,
        time_provider=clock,
    )
    bank = Bank(
        time_provider=clock,
        audit_log=audit_log,
        risk_analyzer=risk_analyzer,
    )
    processor = TransactionProcessor(
        time_provider=clock
    )

    sender_client = Client(
        full_name="Клиент аудита",
        client_id="audit-client-001",
        age=30,
        contacts={"phone": "+79990000101"},
    )
    first_recipient_client = Client(
        full_name="Первый получатель",
        client_id="audit-client-002",
        age=28,
        contacts={"phone": "+79990000102"},
    )
    second_recipient_client = Client(
        full_name="Второй получатель",
        client_id="audit-client-003",
        age=35,
        contacts={"phone": "+79990000103"},
    )

    sender = BankAccount(
        owner=sender_client.full_name,
        balance=Decimal("50000"),
        currency=Currency.RUB,
        account_id="audit-sender-001",
    )
    first_recipient = BankAccount(
        owner=first_recipient_client.full_name,
        balance=Decimal("1000"),
        currency=Currency.RUB,
        account_id="audit-recipient-001",
    )
    second_recipient = BankAccount(
        owner=second_recipient_client.full_name,
        balance=Decimal("1000"),
        currency=Currency.RUB,
        account_id="audit-recipient-002",
    )

    bank.add_client(
        sender_client,
        "sender-password",
    )
    bank.add_client(
        first_recipient_client,
        "first-recipient-password",
    )
    bank.add_client(
        second_recipient_client,
        "second-recipient-password",
    )
    bank.open_account(
        sender_client.client_id,
        sender,
    )
    bank.open_account(
        first_recipient_client.client_id,
        first_recipient,
    )
    bank.open_account(
        second_recipient_client.client_id,
        second_recipient,
    )

    transactions = [
        create_audit_transaction(
            transaction_id="audit-transaction-001",
            sender=sender,
            recipient=first_recipient,
            amount=Decimal("100"),
            created_at=clock.current_time,
        ),
        create_audit_transaction(
            transaction_id="audit-transaction-002",
            sender=sender,
            recipient=first_recipient,
            amount=Decimal("100"),
            created_at=clock.current_time,
        ),
        create_audit_transaction(
            transaction_id="audit-transaction-003",
            sender=sender,
            recipient=first_recipient,
            amount=Decimal("100"),
            created_at=clock.current_time,
        ),
        create_audit_transaction(
            transaction_id="audit-transaction-004",
            sender=sender,
            recipient=second_recipient,
            amount=Decimal("10000"),
            created_at=clock.current_time,
        ),
    ]

    results = []

    for transaction in transactions:
        result = bank.process_transaction(
            transaction,
            processor,
        )
        results.append((transaction, result))

    clock.current_time = datetime(2026, 9, 28, 2, 0)

    night_transaction = create_audit_transaction(
        transaction_id="audit-transaction-005",
        sender=sender,
        recipient=second_recipient,
        amount=Decimal("100"),
        created_at=clock.current_time,
    )
    night_result = bank.process_transaction(
        night_transaction,
        processor,
    )
    results.append((night_transaction, night_result))

    print("\nАудит и анализ рисков:")

    for transaction, result in results:
        print(
            f"{transaction.transaction_id} | "
            f"Выполнена: {result} | "
            f"Статус: {transaction.status.value} | "
            f"Причина: {transaction.failure_reason}"
        )

    print("\nБаланс после риск-проверок:")
    print(f"Отправитель: {sender.balance:.2f} RUB")
    print(
        "Первый получатель:",
        f"{first_recipient.balance:.2f} RUB",
    )
    print(
        "Второй получатель:",
        f"{second_recipient.balance:.2f} RUB",
    )

    report = AuditReport(audit_log)
    suspicious_operations = (
        report.get_suspicious_operations()
    )
    client_profile = report.get_client_risk_profile(
        sender_client.client_id
    )
    error_statistics = report.get_error_statistics()

    print("\nПодозрительные транзакции:")

    for entry in suspicious_operations:
        print(
            entry["transaction_id"],
            entry["details"],
        )

    print("\nРиск-профиль клиента:")
    print(client_profile)

    print("\nСтатистика ошибок:")
    print(error_statistics)

    print("\nФайл аудита: logs/audit.jsonl")

def main() -> None:
    clock = MutableClock(
        datetime(2026, 9, 26, 12, 0)
    )
    bank, clients, accounts = create_demo_bank(clock)

    investment = accounts["investment"]

    if isinstance(investment, InvestmentAccount):
        projected_growth = investment.project_yearly_growth(
            {
                AssetType.STOCKS: Decimal("0.10"),
                AssetType.BONDS: Decimal("0.04"),
                AssetType.ETF: Decimal("0.07"),
            }
        )
        print(
            "Прогнозируемый прирост портфеля:",
            f"{projected_growth:.2f} "
            f"{investment.currency.value}",
        )

    bank.freeze_account(
        accounts["reserve"].account_id
    )

    transactions = create_transactions(
        accounts,
        clock.current_time,
    )
    queue = prepare_transaction_queue(
        transactions,
        clock,
    )
    processor, processed_transactions = (
        process_transactions(queue, clock)
    )

    bank.unfreeze_account(
        accounts["reserve"].account_id
    )

    display_processing_order(processed_transactions)
    display_transactions(transactions)
    display_transaction_summary(transactions)
    display_error_log(processor)
    demonstrate_authentication(bank, clients)
    display_accounts(bank)
    display_analytics(bank)
    display_suspicious_actions(bank)
    demonstrate_night_restriction()
    demonstrate_audit_and_risk()


if __name__ == "__main__":
    main()
