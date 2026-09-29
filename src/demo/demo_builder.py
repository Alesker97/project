from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from src.accounts.account_base import AbstractAccount
from src.accounts.bank_account import BankAccount
from src.accounts.investment_account import InvestmentAccount
from src.accounts.premium_account import PremiumAccount
from src.accounts.savings_account import SavingsAccount
from src.audit.audit_log import AuditLog
from src.banks.bank import Bank
from src.clients.client import Client
from src.enums.currency import Currency
from src.risk.risk_analyzer import RiskAnalyzer
from src.enums.transaction_type import TransactionType
from src.transactions.transaction import Transaction
from src.transactions.transaction_processor import TransactionProcessor
from src.transactions.transaction_queue import TransactionQueue


DEMO_START_TIME = datetime(2026, 9, 29, 12, 0)
DEMO_DELAYED_TIME = datetime(2026, 9, 29, 14, 0)
DEMO_NIGHT_TIME = datetime(2026, 9, 30, 2, 0)
AUDIT_FILE_PATH = Path("logs/audit.jsonl")

DEMO_PASSWORDS = {
    "alexey": "alexey-password",
    "maria": "maria-password",
    "ivan": "ivan-password",
    "elena": "elena-password",
    "dmitry": "dmitry-password",
    "olga": "olga-password",
}

DEMO_ACCOUNT_OWNERS = {
    "alexey_checking": "alexey",
    "alexey_savings": "alexey",
    "maria_premium": "maria",
    "maria_usd": "maria",
    "ivan_investment": "ivan",
    "ivan_checking": "ivan",
    "elena_savings": "elena",
    "elena_eur": "elena",
    "dmitry_premium": "dmitry",
    "dmitry_investment": "dmitry",
    "olga_checking": "olga",
    "olga_savings": "olga",
}

DEMO_TRANSACTION_GROUPS = {
    "completed": frozenset(
        f"demo-tx-{number:03d}"
        for number in range(1, 25)
    ),
    "failed": frozenset(
        f"demo-tx-{number:03d}"
        for number in range(25, 30)
    ),
    "suspicious": frozenset(
        f"demo-tx-{number:03d}"
        for number in range(30, 37)
    ),
    "cancelled": frozenset(
        f"demo-tx-{number:03d}"
        for number in range(37, 41)
    ),
}


class MutableClock:
    def __init__(self, current_time: datetime) -> None:
        self.current_time = current_time

    def __call__(self) -> datetime:
        return self.current_time


def create_demo_clients() -> dict[str, Client]:
    return {
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
        "elena": Client(
            full_name="Елена Смирнова",
            client_id="client-004",
            age=32,
            contacts={
                "phone": "+79990000004",
                "email": "elena@example.com",
            },
        ),
        "dmitry": Client(
            full_name="Дмитрий Волков",
            client_id="client-005",
            age=41,
            contacts={
                "phone": "+79990000005",
                "email": "dmitry@example.com",
            },
        ),
        "olga": Client(
            full_name="Ольга Кузнецова",
            client_id="client-006",
            age=26,
            contacts={
                "phone": "+79990000006",
                "email": "olga@example.com",
            },
        ),
    }


def create_demo_bank(
    clock: MutableClock,
    clients: dict[str, Client],
) -> tuple[Bank, AuditLog, RiskAnalyzer]:
    audit_log = AuditLog(
        file_path=AUDIT_FILE_PATH,
        time_provider=clock,
    )
    risk_analyzer = RiskAnalyzer(
        large_amount_threshold=Decimal("10000"),
        frequent_operations_limit=3,
        frequent_operations_window=timedelta(minutes=5),
        time_provider=clock,
    )
    bank = Bank(
        time_provider=clock,
        audit_log=audit_log,
        risk_analyzer=risk_analyzer,
    )

    for client_key, client in clients.items():
        bank.add_client(
            client,
            DEMO_PASSWORDS[client_key],
        )

    return bank, audit_log, risk_analyzer


def create_demo_accounts(
    clients: dict[str, Client],
) -> dict[str, AbstractAccount]:
    return {
        "alexey_checking": BankAccount(
            owner=clients["alexey"].full_name,
            balance=Decimal("50000"),
            currency=Currency.RUB,
            account_id="demo-acc-0001",
        ),
        "alexey_savings": SavingsAccount(
            owner=clients["alexey"].full_name,
            balance=Decimal("30000"),
            currency=Currency.RUB,
            min_balance=Decimal("5000"),
            monthly_interest_rate=Decimal("0.01"),
            account_id="demo-acc-0002",
        ),
        "maria_premium": PremiumAccount(
            owner=clients["maria"].full_name,
            balance=Decimal("40000"),
            currency=Currency.RUB,
            withdrawal_limit=Decimal("100000"),
            overdraft_limit=Decimal("10000"),
            fixed_commission=Decimal("100"),
            account_id="demo-acc-0003",
        ),
        "maria_usd": BankAccount(
            owner=clients["maria"].full_name,
            balance=Decimal("2000"),
            currency=Currency.USD,
            account_id="demo-acc-0004",
        ),
        "ivan_investment": InvestmentAccount(
            owner=clients["ivan"].full_name,
            balance=Decimal("25000"),
            currency=Currency.USD,
            account_id="demo-acc-0005",
        ),
        "ivan_checking": BankAccount(
            owner=clients["ivan"].full_name,
            balance=Decimal("35000"),
            currency=Currency.RUB,
            account_id="demo-acc-0006",
        ),
        "elena_savings": SavingsAccount(
            owner=clients["elena"].full_name,
            balance=Decimal("20000"),
            currency=Currency.RUB,
            min_balance=Decimal("3000"),
            monthly_interest_rate=Decimal("0.015"),
            account_id="demo-acc-0007",
        ),
        "elena_eur": BankAccount(
            owner=clients["elena"].full_name,
            balance=Decimal("5000"),
            currency=Currency.EUR,
            account_id="demo-acc-0008",
        ),
        "dmitry_premium": PremiumAccount(
            owner=clients["dmitry"].full_name,
            balance=Decimal("60000"),
            currency=Currency.RUB,
            withdrawal_limit=Decimal("150000"),
            overdraft_limit=Decimal("15000"),
            fixed_commission=Decimal("150"),
            account_id="demo-acc-0009",
        ),
        "dmitry_investment": InvestmentAccount(
            owner=clients["dmitry"].full_name,
            balance=Decimal("40000"),
            currency=Currency.RUB,
            account_id="demo-acc-0010",
        ),
        "olga_checking": BankAccount(
            owner=clients["olga"].full_name,
            balance=Decimal("15000"),
            currency=Currency.RUB,
            account_id="demo-acc-0011",
        ),
        "olga_savings": SavingsAccount(
            owner=clients["olga"].full_name,
            balance=Decimal("12000"),
            currency=Currency.RUB,
            min_balance=Decimal("2000"),
            monthly_interest_rate=Decimal("0.01"),
            account_id="demo-acc-0012",
        ),
    }


def register_demo_accounts(
    bank: Bank,
    clients: dict[str, Client],
    accounts: dict[str, AbstractAccount],
) -> None:
    for account_key, account in accounts.items():
        client_key = DEMO_ACCOUNT_OWNERS[account_key]

        bank.open_account(
            clients[client_key].client_id,
            account,
        )


def create_demo_queue(
    clock: MutableClock,
) -> TransactionQueue:
    return TransactionQueue(time_provider=clock)


def create_demo_processor(
    clock: MutableClock,
) -> TransactionProcessor:
    return TransactionProcessor(
        external_commission_rate=Decimal("0.01"),
        conversion_rates={
            (Currency.USD, Currency.RUB): Decimal("80"),
            (Currency.RUB, Currency.USD): Decimal("0.0125"),
        },
        max_retries=2,
        time_provider=clock,
    )


def create_demo_transactions(
    accounts: dict[str, AbstractAccount],
) -> list[Transaction]:
    daytime = DEMO_START_TIME
    internal = TransactionType.INTERNAL_TRANSFER
    external = TransactionType.EXTERNAL_TRANSFER

    def create_transaction(
        transaction_id: str,
        transaction_type: TransactionType,
        amount: str,
        sender_key: str,
        recipient_key: str,
        *,
        created_at: datetime = daytime,
        scheduled_at: datetime | None = None,
    ) -> Transaction:
        sender = accounts[sender_key]

        return Transaction(
            transaction_type=transaction_type,
            amount=Decimal(amount),
            currency=sender.currency,
            sender=sender,
            recipient=accounts[recipient_key],
            transaction_id=transaction_id,
            created_at=created_at,
            scheduled_at=scheduled_at,
        )

    return [
        create_transaction(
            "demo-tx-001",
            internal,
            "500",
            "alexey_checking",
            "maria_premium",
        ),
        create_transaction(
            "demo-tx-002",
            external,
            "600",
            "alexey_checking",
            "maria_premium",
        ),
        create_transaction(
            "demo-tx-003",
            internal,
            "700",
            "alexey_checking",
            "maria_premium",
        ),
        create_transaction(
            "demo-tx-004",
            external,
            "800",
            "alexey_checking",
            "maria_premium",
        ),
        create_transaction(
            "demo-tx-005",
            internal,
            "400",
            "maria_premium",
            "ivan_checking",
        ),
        create_transaction(
            "demo-tx-006",
            external,
            "500",
            "maria_premium",
            "ivan_checking",
        ),
        create_transaction(
            "demo-tx-007",
            internal,
            "600",
            "maria_premium",
            "ivan_checking",
        ),
        create_transaction(
            "demo-tx-008",
            external,
            "700",
            "maria_premium",
            "ivan_checking",
        ),
        create_transaction(
            "demo-tx-009",
            internal,
            "300",
            "ivan_checking",
            "elena_savings",
        ),
        create_transaction(
            "demo-tx-010",
            external,
            "400",
            "ivan_checking",
            "elena_savings",
        ),
        create_transaction(
            "demo-tx-011",
            internal,
            "500",
            "ivan_checking",
            "elena_savings",
        ),
        create_transaction(
            "demo-tx-012",
            external,
            "600",
            "ivan_checking",
            "elena_savings",
        ),
        create_transaction(
            "demo-tx-013",
            internal,
            "200",
            "elena_savings",
            "olga_checking",
        ),
        create_transaction(
            "demo-tx-014",
            external,
            "300",
            "elena_savings",
            "olga_checking",
        ),
        create_transaction(
            "demo-tx-015",
            internal,
            "400",
            "elena_savings",
            "olga_checking",
        ),
        create_transaction(
            "demo-tx-016",
            external,
            "500",
            "elena_savings",
            "olga_checking",
        ),
        create_transaction(
            "demo-tx-017",
            internal,
            "1000",
            "dmitry_premium",
            "alexey_checking",
        ),
        create_transaction(
            "demo-tx-018",
            external,
            "900",
            "dmitry_premium",
            "alexey_checking",
        ),
        create_transaction(
            "demo-tx-019",
            internal,
            "800",
            "dmitry_premium",
            "alexey_checking",
        ),
        create_transaction(
            "demo-tx-020",
            external,
            "700",
            "dmitry_premium",
            "alexey_checking",
        ),
        create_transaction(
            "demo-tx-021",
            internal,
            "500",
            "olga_checking",
            "dmitry_investment",
            scheduled_at=DEMO_DELAYED_TIME,
        ),
        create_transaction(
            "demo-tx-022",
            external,
            "600",
            "olga_checking",
            "dmitry_investment",
            scheduled_at=DEMO_DELAYED_TIME,
        ),
        create_transaction(
            "demo-tx-023",
            internal,
            "100",
            "olga_savings",
            "dmitry_investment",
        ),
        create_transaction(
            "demo-tx-024",
            internal,
            "100",
            "maria_usd",
            "ivan_investment",
        ),
        create_transaction(
            "demo-tx-025",
            internal,
            "5000",
            "maria_usd",
            "ivan_investment",
        ),
        create_transaction(
            "demo-tx-026",
            internal,
            "100",
            "ivan_investment",
            "elena_savings",
        ),
        create_transaction(
            "demo-tx-027",
            internal,
            "100",
            "elena_eur",
            "olga_checking",
        ),
        create_transaction(
            "demo-tx-028",
            internal,
            "9999",
            "olga_savings",
            "dmitry_investment",
        ),
        create_transaction(
            "demo-tx-029",
            internal,
            "100",
            "dmitry_investment",
            "alexey_checking",
        ),
        create_transaction(
            "demo-tx-030",
            internal,
            "10000",
            "alexey_savings",
            "maria_premium",
        ),
        create_transaction(
            "demo-tx-031",
            internal,
            "10000",
            "maria_premium",
            "olga_checking",
        ),
        create_transaction(
            "demo-tx-032",
            internal,
            "10000",
            "ivan_checking",
            "alexey_checking",
        ),
        create_transaction(
            "demo-tx-033",
            internal,
            "10000",
            "elena_savings",
            "dmitry_investment",
        ),
        create_transaction(
            "demo-tx-034",
            internal,
            "10000",
            "dmitry_investment",
            "maria_premium",
        ),
        create_transaction(
            "demo-tx-035",
            internal,
            "10000",
            "olga_checking",
            "alexey_checking",
        ),
        create_transaction(
            "demo-tx-036",
            internal,
            "100",
            "alexey_savings",
            "maria_premium",
            created_at=DEMO_NIGHT_TIME,
            scheduled_at=DEMO_NIGHT_TIME,
        ),
        create_transaction(
            "demo-tx-037",
            internal,
            "250",
            "alexey_checking",
            "ivan_checking",
        ),
        create_transaction(
            "demo-tx-038",
            external,
            "350",
            "maria_premium",
            "elena_savings",
        ),
        create_transaction(
            "demo-tx-039",
            internal,
            "450",
            "ivan_checking",
            "olga_checking",
        ),
        create_transaction(
            "demo-tx-040",
            external,
            "550",
            "dmitry_premium",
            "maria_premium",
        ),
    ]
