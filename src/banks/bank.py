from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from src.accounts.bank_account import BankAccount
from src.clients.client import Client
from src.enums.account_status import AccountStatus
from src.enums.client_status import ClientStatus
from src.enums.currency import Currency
from src.exceptions import InvalidOperationError


class Bank:
    def __init__(
        self,
        time_provider: Callable[[], datetime] | None = None,
    ) -> None:
        if time_provider is not None and not callable(time_provider):
            raise InvalidOperationError(
                "Источник времени должен быть вызываемым объектом."
            )

        self._time_provider = time_provider or datetime.now
        self._clients: dict[str, Client] = {}
        self._accounts: dict[str, BankAccount] = {}
        self._account_owners: dict[str, str] = {}
        self._credentials: dict[str, str] = {}
        self._failed_attempts: dict[str, int] = {}
        self._suspicious_actions: list[dict[str, object]] = []

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
        current_datetime = self._time_provider()

        if 0 <= current_datetime.hour < 5:
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
                "timestamp": timestamp or self._time_provider(),
            }
        )
