import csv
import json
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from src.audit.audit_report import AuditReport
from src.banks.bank import Bank
from src.clients.client import Client
from src.enums.account_status import AccountStatus
from src.enums.currency import Currency
from src.enums.risk_level import RiskLevel
from src.enums.transaction_status import TransactionStatus
from src.transactions.transaction import Transaction


class ReportBuilder:
    def __init__(
        self,
        bank: Bank,
        clients: dict[str, Client],
        transactions: list[Transaction],
        audit_report: AuditReport,
        processing_log: list[dict[str, object]],
    ) -> None:
        self._bank = bank
        self._clients = clients
        self._transactions = transactions
        self._audit_report = audit_report
        self._processing_log = processing_log

    def build_client_report(
        self,
        client: Client,
    ) -> dict[str, object]:
        accounts = self._bank.search_accounts(
            client_id=client.client_id,
        )
        account_ids = {
            account.account_id
            for account in accounts
        }
        transactions = [
            transaction
            for transaction in self._transactions
            if (
                transaction.sender.account_id in account_ids
                or transaction.recipient.account_id in account_ids
            )
        ]

        balances = {
            currency.value: sum(
                (
                    account.balance
                    for account in accounts
                    if account.currency is currency
                ),
                Decimal("0"),
            )
            for currency in Currency
        }
        status_counts = {
            status.value: sum(
                transaction.status is status
                for transaction in transactions
            )
            for status in TransactionStatus
        }
        commissions = {
            currency.value: sum(
                (
                    transaction.commission
                    for transaction in transactions
                    if (
                        transaction.sender.account_id
                        in account_ids
                        and transaction.currency is currency
                        and transaction.status
                        is TransactionStatus.COMPLETED
                    )
                ),
                Decimal("0"),
            )
            for currency in Currency
        }
        history = [
            self._build_history_entry(
                transaction,
                account_ids,
            )
            for transaction in transactions
        ]
        suspicious_operations = [
            operation
            for operation
            in self._audit_report.get_suspicious_operations()
            if operation.get("client_id") == client.client_id
        ]

        return {
            "report_type": "client",
            "client": {
                "client_id": client.client_id,
                "full_name": client.full_name,
                "age": client.age,
                "status": client.status.value,
                "contacts": client.contacts,
            },
            "accounts": {
                "count": len(accounts),
                "items": [
                    account.get_account_info()
                    for account in accounts
                ],
            },
            "balances": balances,
            "transactions": {
                "total": len(transactions),
                "incoming": sum(
                    transaction.recipient.account_id
                    in account_ids
                    for transaction in transactions
                ),
                "outgoing": sum(
                    transaction.sender.account_id
                    in account_ids
                    for transaction in transactions
                ),
                "by_status": status_counts,
                "commissions": commissions,
            },
            "history": history,
            "risk": {
                "profile": (
                    self._audit_report
                    .get_client_risk_profile(
                        client.client_id,
                    )
                ),
                "suspicious_operations": (
                    suspicious_operations
                ),
            },
        }

    def build_bank_report(self) -> dict[str, object]:
        accounts = self._bank.search_accounts()
        total_balances = self._bank.get_total_balance()
        status_counts = {
            status.value: sum(
                transaction.status is status
                for transaction in self._transactions
            )
            for status in TransactionStatus
        }
        account_status_counts = {
            status.value: sum(
                account.status is status
                for account in accounts
            )
            for status in AccountStatus
        }
        account_currency_counts = {
            currency.value: sum(
                account.currency is currency
                for account in accounts
            )
            for currency in Currency
        }
        account_type_counts: dict[str, int] = {}

        for account in accounts:
            account_type = type(account).__name__
            account_type_counts[account_type] = (
                account_type_counts.get(account_type, 0) + 1
            )

        commissions = {
            currency.value: sum(
                (
                    transaction.commission
                    for transaction in self._transactions
                    if (
                        transaction.currency is currency
                        and transaction.status
                        is TransactionStatus.COMPLETED
                    )
                ),
                Decimal("0"),
            )
            for currency in Currency
        }
        top_clients = [
            {
                "client_id": client.client_id,
                "full_name": client.full_name,
                "balance": balance,
                "currency": Currency.RUB.value,
            }
            for client, balance in (
                self._bank.get_clients_ranking(
                    Currency.RUB,
                )[:3]
            )
        ]

        return {
            "report_type": "bank",
            "clients": {
                "count": len(self._clients),
            },
            "accounts": {
                "count": len(accounts),
                "by_type": account_type_counts,
                "by_status": account_status_counts,
                "by_currency": account_currency_counts,
            },
            "balances": {
                currency.value: balance
                for currency, balance
                in total_balances.items()
            },
            "transactions": {
                "total": len(self._transactions),
                "by_status": status_counts,
                "completed": status_counts[
                    TransactionStatus.COMPLETED.value
                ],
                "rejected": status_counts[
                    TransactionStatus.FAILED.value
                ],
                "cancelled": status_counts[
                    TransactionStatus.CANCELLED.value
                ],
                "blocked_by_bank": sum(
                    (
                        transaction.status
                        is TransactionStatus.FAILED
                        and transaction.attempts == 0
                    )
                    for transaction in self._transactions
                ),
                "processor_errors": sum(
                    (
                        transaction.status
                        is TransactionStatus.FAILED
                        and transaction.attempts > 0
                    )
                    for transaction in self._transactions
                ),
                "commissions": commissions,
            },
            "top_clients": top_clients,
            "suspicious_actions": (
                self._bank.suspicious_actions
            ),
            "audit_entries": len(
                self._bank.audit_log
            ),
        }

    def build_risk_report(self) -> dict[str, object]:
        suspicious_operations = (
            self._audit_report
            .get_suspicious_operations()
        )
        error_statistics = (
            self._audit_report
            .get_error_statistics()
        )
        risk_counts = {
            risk_level.value: 0
            for risk_level in RiskLevel
        }
        reason_counts: dict[str, int] = {}

        for operation in suspicious_operations:
            details = operation.get("details")

            if not isinstance(details, dict):
                continue

            risk_level = details.get("risk_level")
            reasons = details.get("reasons", [])

            if isinstance(risk_level, RiskLevel):
                risk_counts[risk_level.value] += 1
            elif (
                isinstance(risk_level, str)
                and risk_level in risk_counts
            ):
                risk_counts[risk_level] += 1

            if isinstance(reasons, list):
                for reason in reasons:
                    if isinstance(reason, str):
                        reason_counts[reason] = (
                            reason_counts.get(reason, 0) + 1
                        )

        client_profiles = {
            client.client_id: (
                self._audit_report
                .get_client_risk_profile(
                    client.client_id,
                )
            )
            for client in self._clients.values()
        }
        errors_by_type = error_statistics.get(
            "by_event_type",
            {},
        )
        blocked_operations = 0

        if isinstance(errors_by_type, dict):
            blocked_operations = errors_by_type.get(
                "transaction_blocked",
                0,
            )

        return {
            "report_type": "risk",
            "suspicious_operations": (
                suspicious_operations
            ),
            "risk_counts": risk_counts,
            "reason_counts": reason_counts,
            "blocked_operations": blocked_operations,
            "client_profiles": client_profiles,
            "error_statistics": error_statistics,
        }

    def build_text_report(
        self,
        report_data: dict[str, object],
    ) -> str:
        normalized_data = self._normalize_value(
            report_data
        )
        lines: list[str] = []

        self._append_text_lines(
            lines,
            normalized_data,
        )

        return "\n".join(lines)

    def export_to_json(
        self,
        report_data: dict[str, object],
        file_path: str | Path,
    ) -> Path:
        path = Path(file_path)
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        normalized_data = self._normalize_value(
            report_data
        )

        with path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                normalized_data,
                file,
                ensure_ascii=False,
                indent=2,
            )

        return path

    def export_to_csv(
        self,
        report_data: dict[str, object],
        file_path: str | Path,
    ) -> Path:
        path = Path(file_path)
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        normalized_data = self._normalize_value(
            report_data
        )

        if not isinstance(normalized_data, dict):
            raise TypeError(
                "Отчёт должен быть словарём."
            )

        rows = self._flatten_for_csv(
            normalized_data
        )

        with path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    "field",
                    "value",
                ]
            )
            writer.writerows(rows)

        return path

    def save_charts(
        self,
        output_dir: str | Path,
        account_id: str,
        currency: Currency = Currency.RUB,
    ) -> dict[str, Path]:
        directory = Path(output_dir)
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        chart_paths = {
            "transaction_statuses_pie": (
                directory
                / "transaction_statuses_pie.png"
            ),
            "client_balances_bar": (
                directory
                / "client_balances_bar.png"
            ),
            "account_balance_history": (
                directory
                / "account_balance_history.png"
            ),
        }

        self._save_transaction_statuses_chart(
            chart_paths["transaction_statuses_pie"]
        )
        self._save_client_balances_chart(
            chart_paths["client_balances_bar"],
            currency,
        )
        self._save_account_balance_chart(
            chart_paths["account_balance_history"],
            account_id,
        )

        return chart_paths

    def _save_transaction_statuses_chart(
        self,
        file_path: Path,
    ) -> None:
        status_counts = {
            status.value: sum(
                transaction.status is status
                for transaction in self._transactions
            )
            for status in TransactionStatus
        }
        status_counts = {
            status: count
            for status, count in status_counts.items()
            if count > 0
        }

        figure = Figure(
            figsize=(8, 6),
        )
        FigureCanvasAgg(figure)
        axes = figure.subplots()

        axes.pie(
            status_counts.values(),
            labels=status_counts.keys(),
            autopct="%1.1f%%",
            startangle=90,
        )
        axes.set_title(
            "Распределение статусов транзакций"
        )
        axes.axis("equal")

        figure.tight_layout()
        figure.savefig(
            file_path,
            dpi=150,
        )
        figure.clear()

    def _save_client_balances_chart(
        self,
        file_path: Path,
        currency: Currency,
    ) -> None:
        ranking = self._bank.get_clients_ranking(
            currency
        )
        client_names = [
            client.full_name
            for client, _ in ranking
        ]
        balances = [
            float(balance)
            for _, balance in ranking
        ]

        figure = Figure(
            figsize=(10, 6),
        )
        FigureCanvasAgg(figure)
        axes = figure.subplots()

        axes.bar(
            client_names,
            balances,
            color="#4C78A8",
        )
        axes.set_title(
            "Балансы клиентов"
        )
        axes.set_xlabel(
            "Клиент"
        )
        axes.set_ylabel(
            f"Баланс, {currency.value}"
        )
        axes.tick_params(
            axis="x",
            rotation=30,
        )
        axes.grid(
            axis="y",
            alpha=0.3,
        )

        figure.tight_layout()
        figure.savefig(
            file_path,
            dpi=150,
        )
        figure.clear()

    def _save_account_balance_chart(
        self,
        file_path: Path,
        account_id: str,
    ) -> None:
        account = next(
            (
                account
                for account
                in self._bank.search_accounts()
                if account.account_id == account_id
            ),
            None,
        )

        if account is None:
            raise ValueError(
                "Счёт для построения графика не найден."
            )

        timestamps: list[datetime] = []
        balances: list[float] = []

        for entry in self._processing_log:
            processed_at = entry.get("processed_at")

            if not isinstance(processed_at, datetime):
                continue

            if (
                entry.get("sender_account_id")
                == account_id
            ):
                balance_before = entry.get(
                    "sender_balance_before"
                )
                balance_after = entry.get(
                    "sender_balance_after"
                )
            elif (
                entry.get("recipient_account_id")
                == account_id
            ):
                balance_before = entry.get(
                    "recipient_balance_before"
                )
                balance_after = entry.get(
                    "recipient_balance_after"
                )
            else:
                continue

            if not isinstance(
                balance_before,
                Decimal,
            ):
                continue

            if not isinstance(
                balance_after,
                Decimal,
            ):
                continue

            if not timestamps:
                timestamps.append(processed_at)
                balances.append(
                    float(balance_before)
                )

            timestamps.append(processed_at)
            balances.append(
                float(balance_after)
            )

        if not timestamps:
            raise ValueError(
                "Для счёта отсутствует история операций."
            )

        figure = Figure(
            figsize=(10, 6),
        )
        FigureCanvasAgg(figure)
        axes = figure.subplots()

        positions = list(
            range(len(timestamps))
        )
        time_labels = [
            timestamp.strftime(
                "%d.%m.%Y %H:%M"
            )
            for timestamp in timestamps
        ]

        axes.plot(
            positions,
            balances,
            marker="o",
            color="#F58518",
            linewidth=2,
        )
        axes.set_title(
            f"Движение баланса счёта {account_id}"
        )
        axes.set_xlabel(
            "Время операции"
        )
        axes.set_ylabel(
            f"Баланс, {account.currency.value}"
        )
        axes.set_xticks(
            positions
        )
        axes.set_xticklabels(
            time_labels,
            rotation=30,
            ha="right",
        )
        axes.grid(
            alpha=0.3,
        )

        figure.tight_layout()
        figure.savefig(
            file_path,
            dpi=150,
        )
        figure.clear()

    def _normalize_value(
        self,
        value: object,
    ) -> object:
        if isinstance(value, Decimal):
            return str(value)

        if isinstance(value, Enum):
            return value.value

        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, Path):
            return str(value)

        if isinstance(value, dict):
            return {
                self._normalize_key(key): (
                    self._normalize_value(item)
                )
                for key, item in value.items()
            }

        if isinstance(value, list):
            return [
                self._normalize_value(item)
                for item in value
            ]

        if isinstance(value, tuple):
            return [
                self._normalize_value(item)
                for item in value
            ]

        return value

    def _normalize_key(
        self,
        value: object,
    ) -> str:
        normalized_value = self._normalize_value(
            value
        )

        return str(normalized_value)

    def _append_text_lines(
        self,
        lines: list[str],
        value: object,
        level: int = 0,
    ) -> None:
        indentation = "  " * level

        if isinstance(value, dict):
            if not value:
                lines.append(f"{indentation}{{}}")
                return

            for key, item in value.items():
                if isinstance(item, (dict, list)):
                    lines.append(
                        f"{indentation}{key}:"
                    )
                    self._append_text_lines(
                        lines,
                        item,
                        level + 1,
                    )
                else:
                    lines.append(
                        f"{indentation}{key}: {item}"
                    )

            return

        if isinstance(value, list):
            if not value:
                lines.append(f"{indentation}[]")
                return

            for item in value:
                if isinstance(item, (dict, list)):
                    lines.append(f"{indentation}-")
                    self._append_text_lines(
                        lines,
                        item,
                        level + 1,
                    )
                else:
                    lines.append(
                        f"{indentation}- {item}"
                    )

            return

        lines.append(f"{indentation}{value}")

    def _flatten_for_csv(
        self,
        report_data: dict[str, object],
        prefix: str = "",
    ) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []

        for key, value in report_data.items():
            field_name = (
                f"{prefix}.{key}"
                if prefix
                else key
            )

            if isinstance(value, dict):
                rows.extend(
                    self._flatten_for_csv(
                        value,
                        field_name,
                    )
                )
            elif isinstance(value, list):
                rows.append(
                    (
                        field_name,
                        json.dumps(
                            value,
                            ensure_ascii=False,
                        ),
                    )
                )
            elif value is None:
                rows.append(
                    (
                        field_name,
                        "",
                    )
                )
            else:
                rows.append(
                    (
                        field_name,
                        str(value),
                    )
                )

        return rows

    def _build_history_entry(
        self,
        transaction: Transaction,
        account_ids: set[str],
    ) -> dict[str, object]:
        sender_is_client = (
            transaction.sender.account_id in account_ids
        )
        recipient_is_client = (
            transaction.recipient.account_id
            in account_ids
        )

        if sender_is_client and recipient_is_client:
            direction = "internal"
        elif sender_is_client:
            direction = "outgoing"
        else:
            direction = "incoming"

        return {
            "transaction_id": transaction.transaction_id,
            "direction": direction,
            "transaction_type": (
                transaction.transaction_type.value
            ),
            "sender_account_id": (
                transaction.sender.account_id
            ),
            "recipient_account_id": (
                transaction.recipient.account_id
            ),
            "amount": transaction.amount,
            "currency": transaction.currency.value,
            "commission": transaction.commission,
            "status": transaction.status.value,
            "failure_reason": (
                transaction.failure_reason
            ),
            "created_at": transaction.created_at,
            "scheduled_at": transaction.scheduled_at,
        }
