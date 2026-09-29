import csv
import json
from pathlib import Path

from src.demo.demo_runner import DemoRunner
from src.audit.audit_report import AuditReport
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
from src.demo.demo_scenarios import (
    prepare_demo_queue,
    run_transaction_simulation,
)
from src.enums.transaction_status import TransactionStatus
from src.reports.report_builder import ReportBuilder


def create_report_builder(
) -> tuple[ReportBuilder, dict[str, Client]]:
    clock = MutableClock(DEMO_START_TIME)
    clients = create_demo_clients()
    bank, _, _ = create_demo_bank(clock, clients)
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
    processing_log = run_transaction_simulation(
        clock,
        queue,
        bank,
        processor,
    )
    audit_report = AuditReport(bank.audit_log)

    report_builder = ReportBuilder(
        bank=bank,
        clients=clients,
        transactions=transactions,
        audit_report=audit_report,
        processing_log=processing_log,
    )

    return report_builder, clients


def test_build_client_report_returns_client_data(
) -> None:
    report_builder, clients = create_report_builder()

    report = report_builder.build_client_report(
        clients["alexey"],
    )

    assert report["report_type"] == "client"
    assert report["client"]["client_id"] == "client-001"
    assert report["client"]["full_name"] == (
        "Алексей Иванов"
    )
    assert report["accounts"]["count"] == 2


def test_build_client_report_returns_transactions(
) -> None:
    report_builder, clients = create_report_builder()

    report = report_builder.build_client_report(
        clients["alexey"],
    )
    transactions = report["transactions"]

    assert transactions["total"] > 0
    assert transactions["incoming"] > 0
    assert transactions["outgoing"] > 0
    assert (
        transactions["by_status"][
            TransactionStatus.COMPLETED.value
        ]
        > 0
    )
    assert len(report["history"]) == (
        transactions["total"]
    )


def test_build_bank_report_returns_bank_statistics(
) -> None:
    report_builder, _ = create_report_builder()

    report = report_builder.build_bank_report()

    assert report["report_type"] == "bank"
    assert report["clients"]["count"] == 6
    assert report["accounts"]["count"] == 12
    assert report["transactions"]["total"] == 40
    assert report["transactions"]["completed"] == 24
    assert report["transactions"]["rejected"] == 12
    assert report["transactions"]["cancelled"] == 4
    assert report["transactions"]["blocked_by_bank"] == 7
    assert report["transactions"]["processor_errors"] == 5
    assert len(report["top_clients"]) == 3


def test_build_risk_report_returns_risk_statistics(
) -> None:
    report_builder, _ = create_report_builder()

    report = report_builder.build_risk_report()

    assert report["report_type"] == "risk"
    assert report["suspicious_operations"]
    assert report["risk_counts"]["medium"] > 0
    assert report["risk_counts"]["high"] > 0
    assert report["blocked_operations"] == 7
    assert len(report["client_profiles"]) == 6


def test_bank_report_contains_every_transaction_status(
) -> None:
    report_builder, _ = create_report_builder()

    report = report_builder.build_bank_report()
    status_counts = report["transactions"]["by_status"]

    assert set(status_counts) == {
        status.value
        for status in TransactionStatus
    }


def test_build_text_report_returns_readable_text(
) -> None:
    report_builder, _ = create_report_builder()
    bank_report = report_builder.build_bank_report()

    text_report = report_builder.build_text_report(
        bank_report
    )

    assert "report_type: bank" in text_report
    assert "clients:" in text_report
    assert "accounts:" in text_report
    assert "transactions:" in text_report
    assert "completed: 24" in text_report


def test_export_to_json_creates_valid_file(
    tmp_path: Path,
) -> None:
    report_builder, clients = create_report_builder()
    client_report = (
        report_builder.build_client_report(
            clients["alexey"],
        )
    )
    file_path = (
        tmp_path
        / "reports"
        / "client_report.json"
    )

    result_path = report_builder.export_to_json(
        client_report,
        file_path,
    )

    with result_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        saved_report = json.load(file)

    assert result_path == file_path
    assert saved_report["report_type"] == "client"
    assert saved_report["client"]["client_id"] == (
        "client-001"
    )
    assert saved_report["client"]["full_name"] == (
        "Алексей Иванов"
    )
    assert isinstance(
        saved_report["balances"]["RUB"],
        str,
    )


def test_export_to_csv_creates_valid_file(
    tmp_path: Path,
) -> None:
    report_builder, _ = create_report_builder()
    risk_report = report_builder.build_risk_report()
    file_path = (
        tmp_path
        / "reports"
        / "risk_report.csv"
    )

    result_path = report_builder.export_to_csv(
        risk_report,
        file_path,
    )

    with result_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        rows = list(
            csv.DictReader(file)
        )

    saved_fields = {
        row["field"]: row["value"]
        for row in rows
    }

    assert result_path == file_path
    assert saved_fields["report_type"] == "risk"
    assert "risk_counts.medium" in saved_fields
    assert "risk_counts.high" in saved_fields
    assert (
        saved_fields["blocked_operations"]
        == "7"
    )


def test_save_charts_creates_three_png_files(
    tmp_path: Path,
) -> None:
    report_builder, _ = create_report_builder()
    output_dir = tmp_path / "charts"

    chart_paths = report_builder.save_charts(
        output_dir=output_dir,
        account_id="demo-acc-0001",
    )

    assert set(chart_paths) == {
        "transaction_statuses_pie",
        "client_balances_bar",
        "account_balance_history",
    }

    for file_path in chart_paths.values():
        assert file_path.exists()
        assert file_path.suffix == ".png"
        assert file_path.parent == output_dir
        assert file_path.stat().st_size > 0


def test_demo_runner_generates_report_files(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    runner = DemoRunner()

    runner.run(
        output_dir=output_dir
    )

    expected_files = [
        output_dir
        / "reports"
        / "client_report.json",
        output_dir
        / "reports"
        / "client_report.csv",
        output_dir
        / "reports"
        / "bank_report.json",
        output_dir
        / "reports"
        / "bank_report.csv",
        output_dir
        / "reports"
        / "risk_report.json",
        output_dir
        / "reports"
        / "risk_report.csv",
        output_dir
        / "charts"
        / "transaction_statuses_pie.png",
        output_dir
        / "charts"
        / "client_balances_bar.png",
        output_dir
        / "charts"
        / "account_balance_history.png",
    ]

    for file_path in expected_files:
        assert file_path.exists()
        assert file_path.stat().st_size > 0
