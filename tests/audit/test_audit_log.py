from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import pytest

from src.audit.audit_log import AuditLog
from src.enums.audit_level import AuditLevel
from src.enums.risk_level import RiskLevel
from src.exceptions import InvalidOperationError


CURRENT_TIME = datetime(2026, 9, 26, 12, 0)

def test_store_entry_in_memory() -> None:
    audit_log = AuditLog(
        time_provider=lambda: CURRENT_TIME
    )

    entry = audit_log.log(
        level=AuditLevel.INFO,
        event_type="transaction_completed",
        message="Транзакция выполнена.",
        client_id="client-001",
        transaction_id="transaction-001",
        details={
            "amount": Decimal("100.00"),
            "risk_level": RiskLevel.LOW,
        },
    )

    assert len(audit_log) == 1
    assert entry["timestamp"] == CURRENT_TIME
    assert entry["level"] is AuditLevel.INFO
    assert entry["event_type"] == "transaction_completed"
    assert entry["message"] == "Транзакция выполнена."
    assert entry["client_id"] == "client-001"
    assert entry["transaction_id"] == "transaction-001"
    assert entry["details"] == {
        "amount": Decimal("100.00"),
        "risk_level": RiskLevel.LOW,
    }

def test_write_entry_to_jsonl_file(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "logs" / "audit.jsonl"
    audit_log = AuditLog(
        file_path=file_path,
        time_provider=lambda: CURRENT_TIME,
    )

    audit_log.log(
        level=AuditLevel.WARNING,
        event_type="risk_assessment",
        message="Обнаружен риск.",
        client_id="client-001",
        transaction_id="transaction-001",
        details={
            "amount": Decimal("10000.00"),
            "risk_level": RiskLevel.MEDIUM,
            "reasons": ["large_amount"],
        },
    )

    lines = file_path.read_text(
        encoding="utf-8"
    ).splitlines()
    saved_entry = json.loads(lines[0])

    assert len(lines) == 1
    assert saved_entry["timestamp"] == (
        CURRENT_TIME.isoformat()
    )
    assert saved_entry["level"] == "warning"
    assert saved_entry["event_type"] == "risk_assessment"
    assert saved_entry["details"]["amount"] == "10000.00"
    assert saved_entry["details"]["risk_level"] == "medium"
    assert saved_entry["details"]["reasons"] == [
        "large_amount"
    ]

def test_append_entries_to_jsonl_file(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "audit.jsonl"
    audit_log = AuditLog(
        file_path=file_path,
        time_provider=lambda: CURRENT_TIME,
    )

    audit_log.log(
        AuditLevel.INFO,
        "first_event",
        "Первое событие.",
    )
    audit_log.log(
        AuditLevel.ERROR,
        "second_event",
        "Второе событие.",
    )

    lines = file_path.read_text(
        encoding="utf-8"
    ).splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["event_type"] == "first_event"
    assert json.loads(lines[1])["event_type"] == "second_event"

def test_filter_entries() -> None:
    audit_log = AuditLog(
        time_provider=lambda: CURRENT_TIME
    )
    audit_log.log(
        AuditLevel.INFO,
        "transaction_completed",
        "Первая операция.",
        client_id="client-001",
        transaction_id="transaction-001",
    )
    audit_log.log(
        AuditLevel.ERROR,
        "transaction_failed",
        "Вторая операция.",
        client_id="client-001",
        transaction_id="transaction-002",
    )
    audit_log.log(
        AuditLevel.ERROR,
        "transaction_failed",
        "Третья операция.",
        client_id="client-002",
        transaction_id="transaction-003",
    )

    result = audit_log.filter(
        level=AuditLevel.ERROR,
        event_type="transaction_failed",
        client_id="client-001",
        transaction_id="transaction-002",
    )

    assert len(result) == 1
    assert result[0]["transaction_id"] == "transaction-002"

def test_filter_entries_by_time_range() -> None:
    audit_log = AuditLog()
    audit_log.log(
        AuditLevel.INFO,
        "first_event",
        "Первое событие.",
        timestamp=datetime(2026, 9, 26, 10, 0),
    )
    audit_log.log(
        AuditLevel.INFO,
        "second_event",
        "Второе событие.",
        timestamp=datetime(2026, 9, 26, 12, 0),
    )
    audit_log.log(
        AuditLevel.INFO,
        "third_event",
        "Третье событие.",
        timestamp=datetime(2026, 9, 26, 14, 0),
    )

    result = audit_log.filter(
        start_time=datetime(2026, 9, 26, 11, 0),
        end_time=datetime(2026, 9, 26, 13, 0),
    )

    assert len(result) == 1
    assert result[0]["event_type"] == "second_event"

def test_entries_property_returns_copy() -> None:
    audit_log = AuditLog(
        time_provider=lambda: CURRENT_TIME
    )
    audit_log.log(
        AuditLevel.INFO,
        "transaction_completed",
        "Транзакция выполнена.",
        details={"amount": "100.00"},
    )

    entries = audit_log.entries
    entries[0]["message"] = "Изменено."
    entries[0]["details"]["amount"] = "999.00"

    original_entry = audit_log.entries[0]

    assert original_entry["message"] == "Транзакция выполнена."
    assert original_entry["details"]["amount"] == "100.00"

@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("level", "info"),
        ("event_type", ""),
        ("message", ""),
        ("client_id", ""),
        ("transaction_id", ""),
        ("details", []),
    ],
)
def test_reject_invalid_log_data(
    field_name: str,
    field_value: object,
) -> None:
    arguments = {
        "level": AuditLevel.INFO,
        "event_type": "test_event",
        "message": "Тестовое событие.",
        "client_id": "client-001",
        "transaction_id": "transaction-001",
        "details": {},
    }
    arguments[field_name] = field_value
    audit_log = AuditLog(
        time_provider=lambda: CURRENT_TIME
    )

    with pytest.raises(InvalidOperationError):
        audit_log.log(**arguments)

def test_reject_invalid_time_range() -> None:
    audit_log = AuditLog()

    with pytest.raises(InvalidOperationError):
        audit_log.filter(
            start_time=datetime(2026, 9, 26, 13, 0),
            end_time=datetime(2026, 9, 26, 12, 0),
        )

def test_reject_unsupported_details_value() -> None:
    audit_log = AuditLog(
        time_provider=lambda: CURRENT_TIME
    )

    with pytest.raises(InvalidOperationError):
        audit_log.log(
            AuditLevel.INFO,
            "test_event",
            "Тестовое событие.",
            details={"unsupported": object()},
        )

def test_reject_invalid_time_provider_result() -> None:
    audit_log = AuditLog(
        time_provider=lambda: "incorrect"
    )

    with pytest.raises(InvalidOperationError):
        audit_log.log(
            AuditLevel.INFO,
            "test_event",
            "Тестовое событие.",
        )
