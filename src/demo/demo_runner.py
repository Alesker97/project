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

    def run(self) -> None:
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
