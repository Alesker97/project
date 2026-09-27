from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from src.accounts.bank_account import BankAccount
from src.audit.audit_log import AuditLog
from src.clients.client import Client
from src.enums.account_status import AccountStatus
from src.enums.audit_level import AuditLevel
from src.enums.client_status import ClientStatus
from src.enums.currency import Currency
from src.enums.risk_level import RiskLevel
from src.enums.transaction_status import TransactionStatus
from src.exceptions import InvalidOperationError
from src.risk.risk_analyzer import RiskAnalyzer
from src.transactions.transaction import Transaction
from src.transactions.transaction_processor import TransactionProcessor


class Bank:
    def __init__(
        self,
        time_provider: Callable[[], datetime] | None = None,
        audit_log: AuditLog | None = None,
        risk_analyzer: RiskAnalyzer | None = None,
    ) -> None:
        if time_provider is not None and not callable(time_provider):
            raise InvalidOperationError(
                "Источник времени должен быть вызываемым объектом."
            )
        if audit_log is not None and not isinstance(
            audit_log,
            AuditLog,
        ):
            raise InvalidOperationError(
                "Передан некорректный журнал аудита."
            )
        if risk_analyzer is not None and not isinstance(
            risk_analyzer,
            RiskAnalyzer,
        ):
            raise InvalidOperationError(
                "Передан некорректный анализатор риска."
            )

        self._time_provider = time_provider or datetime.now
        self._audit_log = (
            audit_log
            if audit_log is not None
            else AuditLog(time_provider=self._time_provider)
        )
        self._risk_analyzer = (
            risk_analyzer
            if risk_analyzer is not None
            else RiskAnalyzer(time_provider=self._time_provider)
        )
        self._clients: dict[str, Client] = {}
        self._accounts: dict[str, BankAccount] = {}
        self._account_owners: dict[str, str] = {}
        self._credentials: dict[str, str] = {}
        self._failed_attempts: dict[str, int] = {}
        self._suspicious_actions: list[dict[str, object]] = []

    @property
    def audit_log(self) -> AuditLog:
        return self._audit_log

    @property
    def suspicious_actions(self) -> list[dict[str, object]]:
        return [
            suspicious_action.copy()
            for suspicious_action in self._suspicious_actions
        ]

    def add_client(
        self,
        client: Client,
        password: str,
    ) -> None:
        if not isinstance(client, Client):
            raise InvalidOperationError(
                "Можно добавить только объект Client."
            )

        if not isinstance(password, str) or not password.strip():
            raise InvalidOperationError(
                "Пароль должен быть непустой строкой."
            )

        if client.client_id in self._clients:
            raise InvalidOperationError(
                "Клиент с таким ID уже существует."
            )

        self._clients[client.client_id] = client
        self._credentials[client.client_id] = password
        self._failed_attempts[client.client_id] = 0

    def open_account(
        self,
        client_id: str,
        account: BankAccount,
    ) -> str:
        client = self._get_active_client(client_id)

        if not isinstance(account, BankAccount):
            raise InvalidOperationError(
                "Можно открыть только банковский счёт."
            )

        if account.owner != client.full_name:
            raise InvalidOperationError(
                "Владелец счёта не соответствует клиенту."
            )

        if account.account_id in self._accounts:
            raise InvalidOperationError(
                "Счёт с таким номером уже существует."
            )

        self._ensure_operation_time_allowed(
            client.client_id,
            "open_account",
        )

        self._accounts[account.account_id] = account
        self._account_owners[account.account_id] = client.client_id
        client._add_account_id(account.account_id)

        return account.account_id

    def close_account(
        self,
        client_id: str,
        account_id: str,
    ) -> None:
        client = self._get_active_client(client_id)
        account = self._get_account(account_id)
        self._ensure_account_owner(client.client_id, account.account_id)
        self._ensure_operation_time_allowed(
            client.client_id,
            "close_account",
        )

        if account.status is AccountStatus.CLOSED:
            raise InvalidOperationError(
                "Счёт уже закрыт."
            )

        account._set_status(AccountStatus.CLOSED)

    def freeze_account(self, account_id: str) -> None:
        account = self._get_account(account_id)
        client_id = self._account_owners[account.account_id]
        self._ensure_operation_time_allowed(
            client_id,
            "freeze_account",
        )

        if account.status is not AccountStatus.ACTIVE:
            raise InvalidOperationError(
                "Заморозить можно только активный счёт."
            )

        account._set_status(AccountStatus.FROZEN)

    def unfreeze_account(self, account_id: str) -> None:
        account = self._get_account(account_id)
        client_id = self._account_owners[account.account_id]
        self._ensure_operation_time_allowed(
            client_id,
            "unfreeze_account",
        )

        if account.status is not AccountStatus.FROZEN:
            raise InvalidOperationError(
                "Разморозить можно только замороженный счёт."
            )

        account._set_status(AccountStatus.ACTIVE)

    def authenticate_client(
        self,
        client_id: str,
        password: str,
    ) -> bool:
        client = self._clients.get(client_id)

        if client is None:
            self._record_suspicious_action(
                client_id,
                "failed_authentication",
            )
            return False

        if client.status is ClientStatus.BLOCKED:
            return False

        if self._credentials[client_id] == password:
            self._failed_attempts[client_id] = 0
            return True

        self._failed_attempts[client_id] += 1
        self._record_suspicious_action(
            client_id,
            "failed_authentication",
        )

        if self._failed_attempts[client_id] >= 3:
            client._set_status(ClientStatus.BLOCKED)

        return False

    def search_accounts(
        self,
        *,
        client_id: str | None = None,
        status: AccountStatus | None = None,
        currency: Currency | None = None,
    ) -> list[BankAccount]:
        if client_id is not None:
            if not isinstance(client_id, str) or not client_id.strip():
                raise InvalidOperationError(
                    "ID клиента должен быть непустой строкой."
                )

            client_id = client_id.strip()

        if status is not None and not isinstance(
            status,
            AccountStatus,
        ):
            raise InvalidOperationError(
                "Передан недопустимый статус счёта."
            )

        if currency is not None and not isinstance(
            currency,
            Currency,
        ):
            raise InvalidOperationError(
                "Передана неподдерживаемая валюта."
            )

        accounts = list(self._accounts.values())

        if client_id is not None:
            accounts = [
                account
                for account in accounts
                if self._account_owners[account.account_id] == client_id
            ]

        if status is not None:
            accounts = [
                account
                for account in accounts
                if account.status is status
            ]

        if currency is not None:
            accounts = [
                account
                for account in accounts
                if account.currency is currency
            ]

        return sorted(
            accounts,
            key=lambda account: account.account_id,
        )

    def get_total_balance(self) -> dict[Currency, Decimal]:
        total_balance = {
            currency: Decimal("0")
            for currency in Currency
        }

        for account in self._accounts.values():
            total_balance[account.currency] += account.balance

        return total_balance

    def get_clients_ranking(
        self,
        currency: Currency,
    ) -> list[tuple[Client, Decimal]]:
        if not isinstance(currency, Currency):
            raise InvalidOperationError(
                "Передана неподдерживаемая валюта."
            )

        client_balances = {
            client_id: Decimal("0")
            for client_id in self._clients
        }

        for account_id, account in self._accounts.items():
            if account.currency is currency:
                client_id = self._account_owners[account_id]
                client_balances[client_id] += account.balance

        ranking = [
            (self._clients[client_id], balance)
            for client_id, balance in client_balances.items()
        ]

        return sorted(
            ranking,
            key=lambda item: (-item[1], item[0].client_id),
        )

    def process_transaction(
        self,
        transaction: Transaction,
        processor: TransactionProcessor,
    ) -> bool:
        if not isinstance(transaction, Transaction):
            raise InvalidOperationError(
                "Передан некорректный объект транзакции."
            )
        if not isinstance(processor, TransactionProcessor):
            raise InvalidOperationError(
                "Передан некорректный обработчик транзакций."
            )
        if transaction.status is not TransactionStatus.PENDING:
            raise InvalidOperationError(
                "Банк может обработать только ожидающую транзакцию."
            )

        sender_account_id = transaction.sender.account_id
        registered_sender = self._accounts.get(sender_account_id)

        if registered_sender is not transaction.sender:
            raise InvalidOperationError(
                "Счёт отправителя не зарегистрирован в банке."
            )

        client_id = self._account_owners[sender_account_id]
        self._get_active_client(client_id)

        self._audit_log.log(
            level=AuditLevel.INFO,
            event_type="transaction_requested",
            message="Получен запрос на выполнение транзакции.",
            client_id=client_id,
            transaction_id=transaction.transaction_id,
            details={
                "amount": transaction.amount,
                "currency": transaction.currency,
                "sender_account_id": sender_account_id,
                "recipient_account_id": (
                    transaction.recipient.account_id
                ),
                "transaction_type": transaction.transaction_type,
            },
        )

        risk_result = self._risk_analyzer.analyze(
            transaction,
            client_id,
            self._audit_log,
        )
        risk_level = risk_result.get("risk_level")
        reasons = risk_result.get("reasons")

        if (
            not isinstance(risk_level, RiskLevel)
            or not isinstance(reasons, list)
            or not all(
                isinstance(reason, str)
                for reason in reasons
            )
        ):
            raise InvalidOperationError(
                "Анализатор риска вернул некорректный результат."
            )

        self._audit_log.log(
            level=self._get_risk_audit_level(risk_level),
            event_type="risk_assessment",
            message="Выполнена оценка риска транзакции.",
            client_id=client_id,
            transaction_id=transaction.transaction_id,
            details={
                "risk_level": risk_level,
                "reasons": reasons,
                "amount": transaction.amount,
                "currency": transaction.currency,
                "recipient_account_id": (
                    transaction.recipient.account_id
                ),
            },
        )

        current_datetime = self._get_current_time()

        if self._is_night_time(current_datetime):
            failure_reason = (
                "Переводы запрещены с 00:00 до 05:00."
            )
            transaction._mark_failed(
                failure_reason,
                current_datetime,
            )
            self._record_suspicious_action(
                client_id,
                "night_transaction",
                current_datetime,
            )
            self._audit_log.log(
                level=AuditLevel.CRITICAL,
                event_type="transaction_blocked",
                message=failure_reason,
                client_id=client_id,
                transaction_id=transaction.transaction_id,
                details={
                    "risk_level": risk_level,
                    "reasons": reasons,
                    "block_reason": "night_operation",
                    "amount": transaction.amount,
                    "currency": transaction.currency,
                    "recipient_account_id": (
                        transaction.recipient.account_id
                    ),
                },
                timestamp=current_datetime,
            )
            return False

        if risk_level is RiskLevel.HIGH:
            failure_reason = (
                "Операция заблокирована банком: "
                "высокий уровень риска."
            )
            transaction._mark_failed(
                failure_reason,
                self._get_current_time(),
            )
            self._audit_log.log(
                level=AuditLevel.CRITICAL,
                event_type="transaction_blocked",
                message=failure_reason,
                client_id=client_id,
                transaction_id=transaction.transaction_id,
                details={
                    "risk_level": risk_level,
                    "reasons": reasons,
                    "amount": transaction.amount,
                    "currency": transaction.currency,
                    "recipient_account_id": (
                        transaction.recipient.account_id
                    ),
                },
            )
            return False

        result = processor.process(transaction)

        if result:
            self._audit_log.log(
                level=AuditLevel.INFO,
                event_type="transaction_completed",
                message="Транзакция успешно выполнена.",
                client_id=client_id,
                transaction_id=transaction.transaction_id,
                details={
                    "amount": transaction.amount,
                    "commission": transaction.commission,
                    "currency": transaction.currency,
                    "recipient_account_id": (
                        transaction.recipient.account_id
                    ),
                    "risk_level": risk_level,
                },
            )
            return True

        self._audit_log.log(
            level=AuditLevel.ERROR,
            event_type="transaction_failed",
            message="Транзакция завершена с ошибкой.",
            client_id=client_id,
            transaction_id=transaction.transaction_id,
            details={
                "amount": transaction.amount,
                "currency": transaction.currency,
                "recipient_account_id": (
                    transaction.recipient.account_id
                ),
                "risk_level": risk_level,
                "failure_reason": transaction.failure_reason,
            },
        )
        return False

    def _get_client(self, client_id: str) -> Client:
        if not isinstance(client_id, str) or not client_id.strip():
            raise InvalidOperationError(
                "ID клиента должен быть непустой строкой."
            )

        normalized_client_id = client_id.strip()
        client = self._clients.get(normalized_client_id)

        if client is None:
            raise InvalidOperationError(
                "Клиент не найден."
            )

        return client

    def _get_active_client(self, client_id: str) -> Client:
        client = self._get_client(client_id)

        if client.status is ClientStatus.BLOCKED:
            raise InvalidOperationError(
                "Клиент заблокирован."
            )

        return client

    def _get_account(self, account_id: str) -> BankAccount:
        if not isinstance(account_id, str) or not account_id.strip():
            raise InvalidOperationError(
                "Номер счёта должен быть непустой строкой."
            )

        normalized_account_id = account_id.strip()
        account = self._accounts.get(normalized_account_id)

        if account is None:
            raise InvalidOperationError(
                "Счёт не найден."
            )

        return account

    @staticmethod
    def _get_risk_audit_level(
        risk_level: RiskLevel,
    ) -> AuditLevel:
        levels = {
            RiskLevel.LOW: AuditLevel.INFO,
            RiskLevel.MEDIUM: AuditLevel.WARNING,
            RiskLevel.HIGH: AuditLevel.CRITICAL,
        }
        return levels[risk_level]

    def _get_current_time(self) -> datetime:
        current_time = self._time_provider()

        if not isinstance(current_time, datetime):
            raise InvalidOperationError(
                "Источник времени должен возвращать datetime."
            )

        return current_time

    @staticmethod
    def _is_night_time(current_datetime: datetime) -> bool:
        return 0 <= current_datetime.hour < 5
    
    def _ensure_account_owner(
        self,
        client_id: str,
        account_id: str,
    ) -> None:
        if self._account_owners[account_id] != client_id:
            raise InvalidOperationError(
                "Счёт не принадлежит клиенту."
            )

    def _ensure_operation_time_allowed(
        self,
        client_id: str,
        action: str,
    ) -> None:
        current_datetime = self._get_current_time()

        if self._is_night_time(current_datetime):
            self._record_suspicious_action(
                client_id,
                f"night_{action}",
                current_datetime,
            )
            raise InvalidOperationError(
                "Операции запрещены с 00:00 до 05:00."
            )

    def _record_suspicious_action(
        self,
        client_id: str,
        action: str,
        timestamp: datetime | None = None,
    ) -> None:
        self._suspicious_actions.append(
            {
                "client_id": client_id,
                "action": action,
                "timestamp": timestamp or self._get_current_time(),
            }
        )
