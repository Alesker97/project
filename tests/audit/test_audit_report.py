from datetime import datetime
import pytest

from src.audit.audit_log import AuditLog
from src.audit.audit_report import AuditReport
from src.enums.audit_level import AuditLevel
from src.enums.risk_level import RiskLevel
from src.exceptions import InvalidOperationError


CURRENT_TIME = datetime(2026, 9, 26, 12, 0)

def add_risk_entry(
    audit_log: AuditLog,
    client_id: str,
    transaction_id: str,
    risk_level: RiskLevel,
) -> None:
    level_mapping = {
        RiskLevel.LOW: AuditLevel.INFO,
        RiskLevel.MEDIUM: AuditLevel.WARNING,
        RiskLevel.HIGH: AuditLevel.CRITICAL,
    }
    audit_log.log(
        level=level_mapping[risk_level],
        event_type="risk_assessment",
        message="Выполнена оценка риска.",
        client_id=client_id,
        transaction_id=transaction_id,
        details={
            "risk_level": risk_level,
            "reasons": [],
        },
        timestamp=CURRENT_TIME,
    )

def test_get_suspicious_operations() -> None:
    audit_log = AuditLog()
    add_risk_entry(
        audit_log,
        "client-001",
        "transaction-low",
        RiskLevel.LOW,
    )
    add_risk_entry(
        audit_log,
        "client-001",
        "transaction-medium",
        RiskLevel.MEDIUM,
    )
    add_risk_entry(
        audit_log,
        "client-002",
        "transaction-high",
        RiskLevel.HIGH,
    )
    report = AuditReport(audit_log)

    suspicious_operations = (
        report.get_suspicious_operations()
    )

    assert len(suspicious_operations) == 2
    assert [
        entry["transaction_id"]
        for entry in suspicious_operations
    ] == [
        "transaction-medium",
        "transaction-high",
    ]

def test_get_client_risk_profile() -> None:
    audit_log = AuditLog()
    add_risk_entry(
        audit_log,
        "client-001",
        "transaction-low",
        RiskLevel.LOW,
    )
    add_risk_entry(
        audit_log,
        "client-001",
        "transaction-medium",
        RiskLevel.MEDIUM,
    )
    add_risk_entry(
        audit_log,
        "client-001",
        "transaction-high",
        RiskLevel.HIGH,
    )
    add_risk_entry(
        audit_log,
        "client-002",
        "other-client-transaction",
        RiskLevel.HIGH,
    )
    audit_log.log(
        level=AuditLevel.CRITICAL,
        event_type="transaction_blocked",
        message="Транзакция заблокирована.",
        client_id="client-001",
        transaction_id="transaction-high",
        timestamp=CURRENT_TIME,
    )
    report = AuditReport(audit_log)

    profile = report.get_client_risk_profile("client-001")

    assert profile == {
        "client_id": "client-001",
        "total_operations": 3,
        "risk_counts": {
            "low": 1,
            "medium": 1,
            "high": 1,
        },
        "blocked_operations": 1,
        "maximum_risk": RiskLevel.HIGH,
    }

def test_get_empty_client_risk_profile() -> None:
    report = AuditReport(AuditLog())

    profile = report.get_client_risk_profile("client-001")

    assert profile == {
        "client_id": "client-001",
        "total_operations": 0,
        "risk_counts": {
            "low": 0,
            "medium": 0,
            "high": 0,
        },
        "blocked_operations": 0,
        "maximum_risk": None,
    }

def test_get_error_statistics() -> None:
    audit_log = AuditLog()
    audit_log.log(
        level=AuditLevel.INFO,
        event_type="transaction_completed",
        message="Транзакция выполнена.",
        timestamp=CURRENT_TIME,
    )
    audit_log.log(
        level=AuditLevel.ERROR,
        event_type="transaction_failed",
        message="Ошибка первой транзакции.",
        timestamp=CURRENT_TIME,
    )
    audit_log.log(
        level=AuditLevel.ERROR,
        event_type="transaction_failed",
        message="Ошибка второй транзакции.",
        timestamp=CURRENT_TIME,
    )
    audit_log.log(
        level=AuditLevel.CRITICAL,
        event_type="transaction_blocked",
        message="Транзакция заблокирована.",
        timestamp=CURRENT_TIME,
    )
    audit_log.log(
        level=AuditLevel.CRITICAL,
        event_type="risk_assessment",
        message="Обнаружен высокий риск.",
        timestamp=CURRENT_TIME,
    )
    report = AuditReport(audit_log)

    statistics = report.get_error_statistics()

    assert statistics == {
        "total_errors": 4,
        "by_event_type": {
            "transaction_failed": 2,
            "transaction_blocked": 1,
            "risk_assessment": 1,
        },
    }

def test_support_string_risk_level() -> None:
    audit_log = AuditLog()
    audit_log.log(
        level=AuditLevel.WARNING,
        event_type="risk_assessment",
        message="Обнаружен средний риск.",
        client_id="client-001",
        transaction_id="transaction-001",
        details={
            "risk_level": "medium",
            "reasons": ["new_recipient"],
        },
        timestamp=CURRENT_TIME,
    )
    report = AuditReport(audit_log)

    suspicious_operations = (
        report.get_suspicious_operations()
    )

    assert len(suspicious_operations) == 1
    assert suspicious_operations[0]["transaction_id"] == (
        "transaction-001"
    )

def test_ignore_invalid_risk_level() -> None:
    audit_log = AuditLog()
    audit_log.log(
        level=AuditLevel.WARNING,
        event_type="risk_assessment",
        message="Некорректная оценка.",
        client_id="client-001",
        transaction_id="transaction-001",
        details={
            "risk_level": "unknown",
        },
        timestamp=CURRENT_TIME,
    )
    report = AuditReport(audit_log)

    suspicious_operations = (
        report.get_suspicious_operations()
    )
    profile = report.get_client_risk_profile("client-001")

    assert suspicious_operations == []
    assert profile["total_operations"] == 0
    assert profile["maximum_risk"] is None

def test_reject_invalid_audit_log() -> None:
    with pytest.raises(InvalidOperationError):
        AuditReport("incorrect")

@pytest.mark.parametrize(
    "client_id",
    ["", "   ", None, 123],
)
def test_reject_invalid_client_id(
    client_id: object,
) -> None:
    report = AuditReport(AuditLog())

    with pytest.raises(InvalidOperationError):
        report.get_client_risk_profile(client_id)
