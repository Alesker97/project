from datetime import datetime
from datetime import timedelta
from decimal import Decimal
import pytest

from src.accounts.bank_account import BankAccount
from src.audit.audit_log import AuditLog
from src.enums.audit_level import AuditLevel
from src.enums.currency import Currency
from src.enums.risk_level import RiskLevel
from src.enums.transaction_type import TransactionType
from src.exceptions import InvalidOperationError
from src.risk.risk_analyzer import RiskAnalyzer
from src.transactions.transaction import Transaction


CURRENT_TIME = datetime(2026, 9, 26, 12, 0)

def create_transaction(
    transaction_id: str = "transaction-001",
    amount: Decimal = Decimal("100"),
    recipient_id: str = "recipient-001",
    created_at: datetime = CURRENT_TIME,
) -> Transaction:
    sender = BankAccount(
        owner="Отправитель",
        balance=Decimal("100000"),
        currency=Currency.RUB,
        account_id="sender-001",
    )
    recipient = BankAccount(
        owner="Получатель",
        balance=Decimal("1000"),
        currency=Currency.RUB,
        account_id=recipient_id,
    )

    return Transaction(
        transaction_type=TransactionType.INTERNAL_TRANSFER,
        amount=amount,
        currency=Currency.RUB,
        sender=sender,
        recipient=recipient,
        transaction_id=transaction_id,
        created_at=created_at,
    )

def add_known_recipient(
    audit_log: AuditLog,
    recipient_id: str = "recipient-001",
    timestamp: datetime = CURRENT_TIME,
) -> None:
    audit_log.log(
        level=AuditLevel.INFO,
        event_type="transaction_completed",
        message="Транзакция выполнена.",
        client_id="client-001",
        transaction_id="previous-transaction",
        details={
            "recipient_account_id": recipient_id,
        },
        timestamp=timestamp,
    )

def test_detect_low_risk_operation() -> None:
    audit_log = AuditLog()
    add_known_recipient(audit_log)
    analyzer = RiskAnalyzer(
        time_provider=lambda: CURRENT_TIME
    )
    transaction = create_transaction()

    result = analyzer.analyze(
        transaction,
        "client-001",
        audit_log,
    )

    assert result["risk_level"] is RiskLevel.LOW
    assert result["reasons"] == []

def test_detect_new_recipient() -> None:
    audit_log = AuditLog()
    analyzer = RiskAnalyzer(
        time_provider=lambda: CURRENT_TIME
    )
    transaction = create_transaction()

    result = analyzer.analyze(
        transaction,
        "client-001",
        audit_log,
    )

    assert result["risk_level"] is RiskLevel.MEDIUM
    assert result["reasons"] == ["new_recipient"]

def test_detect_large_amount() -> None:
    audit_log = AuditLog()
    add_known_recipient(audit_log)
    analyzer = RiskAnalyzer(
        large_amount_threshold=Decimal("10000"),
        time_provider=lambda: CURRENT_TIME,
    )
    transaction = create_transaction(
        amount=Decimal("10000")
    )

    result = analyzer.analyze(
        transaction,
        "client-001",
        audit_log,
    )

    assert result["risk_level"] is RiskLevel.MEDIUM
    assert result["reasons"] == ["large_amount"]

def test_detect_frequent_operations() -> None:
    audit_log = AuditLog()
    add_known_recipient(audit_log)

    for index in range(3):
        audit_log.log(
            level=AuditLevel.INFO,
            event_type="transaction_requested",
            message="Запрошена транзакция.",
            client_id="client-001",
            transaction_id=f"request-{index}",
            timestamp=(
                CURRENT_TIME - timedelta(minutes=index)
            ),
        )

    analyzer = RiskAnalyzer(
        frequent_operations_limit=3,
        frequent_operations_window=timedelta(minutes=5),
        time_provider=lambda: CURRENT_TIME,
    )
    transaction = create_transaction()

    result = analyzer.analyze(
        transaction,
        "client-001",
        audit_log,
    )

    assert result["risk_level"] is RiskLevel.MEDIUM
    assert result["reasons"] == ["frequent_operations"]

def test_ignore_operations_outside_frequency_window() -> None:
    audit_log = AuditLog()
    add_known_recipient(audit_log)
    audit_log.log(
        level=AuditLevel.INFO,
        event_type="transaction_requested",
        message="Старая транзакция.",
        client_id="client-001",
        transaction_id="old-request",
        timestamp=CURRENT_TIME - timedelta(minutes=6),
    )
    analyzer = RiskAnalyzer(
        frequent_operations_limit=1,
        frequent_operations_window=timedelta(minutes=5),
        time_provider=lambda: CURRENT_TIME,
    )
    transaction = create_transaction()

    result = analyzer.analyze(
        transaction,
        "client-001",
        audit_log,
    )

    assert result["risk_level"] is RiskLevel.LOW
    assert result["reasons"] == []

def test_detect_night_operation() -> None:
    night_time = datetime(2026, 9, 27, 2, 0)
    audit_log = AuditLog()
    add_known_recipient(
        audit_log,
        timestamp=datetime(2026, 9, 26, 12, 0),
    )
    analyzer = RiskAnalyzer(
        time_provider=lambda: night_time
    )
    transaction = create_transaction(
        created_at=night_time
    )

    result = analyzer.analyze(
        transaction,
        "client-001",
        audit_log,
    )

    assert result["risk_level"] is RiskLevel.MEDIUM
    assert result["reasons"] == ["night_operation"]

def test_detect_high_risk_for_large_new_transfer() -> None:
    audit_log = AuditLog()
    analyzer = RiskAnalyzer(
        large_amount_threshold=Decimal("10000"),
        time_provider=lambda: CURRENT_TIME,
    )
    transaction = create_transaction(
        amount=Decimal("10000")
    )

    result = analyzer.analyze(
        transaction,
        "client-001",
        audit_log,
    )

    assert result["risk_level"] is RiskLevel.HIGH
    assert result["reasons"] == [
        "large_amount",
        "new_recipient",
    ]

def test_detect_high_risk_for_night_new_transfer() -> None:
    night_time = datetime(2026, 9, 27, 2, 0)
    audit_log = AuditLog()
    analyzer = RiskAnalyzer(
        time_provider=lambda: night_time
    )
    transaction = create_transaction(
        created_at=night_time
    )

    result = analyzer.analyze(
        transaction,
        "client-001",
        audit_log,
    )

    assert result["risk_level"] is RiskLevel.HIGH
    assert result["reasons"] == [
        "new_recipient",
        "night_operation",
    ]

def test_failed_transfer_does_not_make_recipient_known() -> None:
    audit_log = AuditLog()
    audit_log.log(
        level=AuditLevel.ERROR,
        event_type="transaction_failed",
        message="Транзакция отклонена.",
        client_id="client-001",
        transaction_id="failed-transaction",
        details={
            "recipient_account_id": "recipient-001",
        },
        timestamp=CURRENT_TIME,
    )
    analyzer = RiskAnalyzer(
        time_provider=lambda: CURRENT_TIME
    )
    transaction = create_transaction()

    result = analyzer.analyze(
        transaction,
        "client-001",
        audit_log,
    )

    assert result["risk_level"] is RiskLevel.MEDIUM
    assert result["reasons"] == ["new_recipient"]

def test_use_custom_risk_limits() -> None:
    audit_log = AuditLog()
    add_known_recipient(audit_log)

    for index in range(2):
        audit_log.log(
            level=AuditLevel.INFO,
            event_type="transaction_requested",
            message="Запрошена транзакция.",
            client_id="client-001",
            transaction_id=f"request-{index}",
            timestamp=CURRENT_TIME,
        )

    analyzer = RiskAnalyzer(
        large_amount_threshold=Decimal("500"),
        frequent_operations_limit=2,
        frequent_operations_window=timedelta(minutes=10),
        time_provider=lambda: CURRENT_TIME,
    )
    transaction = create_transaction(
        amount=Decimal("500")
    )

    result = analyzer.analyze(
        transaction,
        "client-001",
        audit_log,
    )

    assert result["risk_level"] is RiskLevel.HIGH
    assert result["reasons"] == [
        "large_amount",
        "frequent_operations",
    ]

@pytest.mark.parametrize(
    "threshold",
    [
        Decimal("0"),
        Decimal("-1"),
        True,
        "incorrect",
        Decimal("NaN"),
    ],
)
def test_reject_invalid_large_amount_threshold(
    threshold: Decimal | str | bool,
) -> None:
    with pytest.raises(InvalidOperationError):
        RiskAnalyzer(large_amount_threshold=threshold)

@pytest.mark.parametrize(
    "limit",
    [0, -1, 1.5, True],
)
def test_reject_invalid_frequency_limit(
    limit: int | float | bool,
) -> None:
    with pytest.raises(InvalidOperationError):
        RiskAnalyzer(frequent_operations_limit=limit)

@pytest.mark.parametrize(
    "window",
    [
        timedelta(0),
        timedelta(minutes=-1),
        "incorrect",
    ],
)
def test_reject_invalid_frequency_window(
    window: timedelta | str,
) -> None:
    with pytest.raises(InvalidOperationError):
        RiskAnalyzer(frequent_operations_window=window)

def test_reject_invalid_analysis_data() -> None:
    analyzer = RiskAnalyzer(
        time_provider=lambda: CURRENT_TIME
    )
    transaction = create_transaction()
    audit_log = AuditLog()

    with pytest.raises(InvalidOperationError):
        analyzer.analyze(
            "incorrect",
            "client-001",
            audit_log,
        )

    with pytest.raises(InvalidOperationError):
        analyzer.analyze(
            transaction,
            "",
            audit_log,
        )

    with pytest.raises(InvalidOperationError):
        analyzer.analyze(
            transaction,
            "client-001",
            "incorrect",
        )

def test_reject_invalid_time_provider_result() -> None:
    analyzer = RiskAnalyzer(
        time_provider=lambda: "incorrect"
    )
    transaction = create_transaction()
    audit_log = AuditLog()

    with pytest.raises(InvalidOperationError):
        analyzer.analyze(
            transaction,
            "client-001",
            audit_log,
        )
