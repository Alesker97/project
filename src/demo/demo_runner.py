from pathlib import Path

from src.reports.report_builder import ReportBuilder
from src.audit.audit_report import AuditReport
from src.demo.demo_builder import (
    AUDIT_FILE_PATH,
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
)
from src.demo.demo_scenarios import (
    prepare_demo_queue,
    run_transaction_simulation,
)
from src.enums.currency import Currency


class DemoRunner:
    def __init__(self) -> None:
        self.clock = MutableClock(DEMO_START_TIME)
        self.clients = create_demo_clients()
        (
            self.bank,
            self.audit_log,
            self.risk_analyzer,
        ) = create_demo_bank(
            self.clock,
            self.clients,
        )
        self.accounts = create_demo_accounts(
            self.clients
        )
        register_demo_accounts(
            self.bank,
            self.clients,
            self.accounts,
        )
        self.transactions = create_demo_transactions(
            self.accounts
        )
        self.queue = create_demo_queue(self.clock)
        self.processor = create_demo_processor(self.clock)
        self.audit_report = AuditReport(self.audit_log)
        self.queue_log: list[dict[str, object]] = []
        self.processing_log: list[dict[str, object]] = []

    def run(
        self,
        output_dir: str | Path = "output",
    ) -> None:
        self.display_initialization()

        self.queue_log = prepare_demo_queue(
            self.queue,
            self.transactions,
        )
        display_queue_log(self.queue_log)

        self.processing_log = run_transaction_simulation(
            self.clock,
            self.queue,
            self.bank,
            self.processor,
        )
        display_processing_log(self.processing_log)

        selected_client = self.clients["alexey"]

        display_client_accounts(
            self.bank,
            selected_client,
        )
        display_client_history(
            selected_client,
            self.transactions,
        )
        display_suspicious_operations(
            self.audit_report
        )
        display_client_risk_profile(
            self.audit_report,
            selected_client,
        )
        display_top_clients(
            self.bank,
            Currency.RUB,
        )
        display_transaction_statistics(
            self.transactions
        )
        display_total_balance(self.bank)
        display_error_statistics(
            self.audit_report
        )
        self.display_suspicious_actions()
        self.display_audit_file()

        generated_files = self.generate_reports(
            output_dir
        )
        self.display_generated_files(
            generated_files
        )
    
    def generate_reports(
        self,
        output_dir: str | Path,
    ) -> dict[str, Path]:
        directory = Path(output_dir)
        reports_directory = directory / "reports"
        charts_directory = directory / "charts"

        report_builder = ReportBuilder(
            bank=self.bank,
            clients=self.clients,
            transactions=self.transactions,
            audit_report=self.audit_report,
            processing_log=self.processing_log,
        )

        client_report = (
            report_builder.build_client_report(
                self.clients["alexey"],
            )
        )
        bank_report = (
            report_builder.build_bank_report()
        )
        risk_report = (
            report_builder.build_risk_report()
        )

        print("\nТекстовый отчёт по клиенту:")
        print(
            report_builder.build_text_report(
                client_report
            )
        )

        generated_files = {
            "client_json": (
                report_builder.export_to_json(
                    client_report,
                    reports_directory
                    / "client_report.json",
                )
            ),
            "client_csv": (
                report_builder.export_to_csv(
                    client_report,
                    reports_directory
                    / "client_report.csv",
                )
            ),
            "bank_json": (
                report_builder.export_to_json(
                    bank_report,
                    reports_directory
                    / "bank_report.json",
                )
            ),
            "bank_csv": (
                report_builder.export_to_csv(
                    bank_report,
                    reports_directory
                    / "bank_report.csv",
                )
            ),
            "risk_json": (
                report_builder.export_to_json(
                    risk_report,
                    reports_directory
                    / "risk_report.json",
                )
            ),
            "risk_csv": (
                report_builder.export_to_csv(
                    risk_report,
                    reports_directory
                    / "risk_report.csv",
                )
            ),
        }

        chart_paths = report_builder.save_charts(
            output_dir=charts_directory,
            account_id="demo-acc-0001",
            currency=Currency.RUB,
        )
        generated_files.update(chart_paths)

        return generated_files

    @staticmethod
    def display_generated_files(
        generated_files: dict[str, Path],
    ) -> None:
        print("\nСозданные файлы отчётности:")

        for file_type, file_path in (
            generated_files.items()
        ):
            print(
                f"{file_type}: {file_path}"
            )

    def display_initialization(self) -> None:
        print("Комплексная демонстрация банковской системы")
        print(f"Клиентов: {len(self.clients)}")
        print(f"Счетов: {len(self.accounts)}")
        print(f"Транзакций: {len(self.transactions)}")

    def display_suspicious_actions(self) -> None:
        print("\nПодозрительные действия банка:")

        if not self.bank.suspicious_actions:
            print("Подозрительные действия отсутствуют.")
            return

        for action in self.bank.suspicious_actions:
            print(
                f'Клиент: {action["client_id"]} | '
                f'Действие: {action["action"]} | '
                f'Время: {action["timestamp"]}'
            )

    @staticmethod
    def display_audit_file() -> None:
        print(f"\nФайл аудита: {AUDIT_FILE_PATH}")
