from src.enums.client_status import ClientStatus
from src.exceptions import InvalidOperationError


class Client:
    def __init__(
        self,
        full_name: str,
        client_id: str,
        age: int,
        contacts: dict[str, str],
        status: ClientStatus = ClientStatus.ACTIVE,
    ) -> None:
        self._full_name = self._validate_full_name(full_name)
        self._client_id = self._validate_client_id(client_id)
        self._age = self._validate_age(age)
        self._contacts = self._validate_contacts(contacts)
        self._status = self._validate_status(status)
        self._account_ids: list[str] = []

    @property
    def full_name(self) -> str:
        return self._full_name

    @property
    def client_id(self) -> str:
        return self._client_id

    @property
    def age(self) -> int:
        return self._age

    @property
    def contacts(self) -> dict[str, str]:
        return self._contacts.copy()

    @property
    def status(self) -> ClientStatus:
        return self._status

    @property
    def account_ids(self) -> list[str]:
        return self._account_ids.copy()

    @staticmethod
    def _validate_full_name(full_name: str) -> str:
        if not isinstance(full_name, str) or not full_name.strip():
            raise InvalidOperationError(
                "ФИО клиента должно быть непустой строкой."
            )

        return full_name.strip()

    @staticmethod
    def _validate_client_id(client_id: str) -> str:
        if not isinstance(client_id, str) or not client_id.strip():
            raise InvalidOperationError(
                "ID клиента должен быть непустой строкой."
            )

        return client_id.strip()

    @staticmethod
    def _validate_age(age: int) -> int:
        if isinstance(age, bool) or not isinstance(age, int):
            raise InvalidOperationError(
                "Возраст клиента должен быть целым числом."
            )

        if age < 18:
            raise InvalidOperationError(
                "Возраст клиента должен быть не меньше 18 лет."
            )

        return age

    @staticmethod
    def _validate_contacts(
        contacts: dict[str, str],
    ) -> dict[str, str]:
        if not isinstance(contacts, dict) or not contacts:
            raise InvalidOperationError(
                "Контакты должны быть переданы непустым словарём."
            )

        normalized_contacts: dict[str, str] = {}

        for contact_type, contact_value in contacts.items():
            if (
                not isinstance(contact_type, str)
                or not contact_type.strip()
                or not isinstance(contact_value, str)
                or not contact_value.strip()
            ):
                raise InvalidOperationError(
                    "Типы и значения контактов должны быть "
                    "непустыми строками."
                )

            normalized_contacts[contact_type.strip()] = (
                contact_value.strip()
            )

        return normalized_contacts

    @staticmethod
    def _validate_status(status: ClientStatus) -> ClientStatus:
        if not isinstance(status, ClientStatus):
            raise InvalidOperationError(
                "Передан недопустимый статус клиента."
            )

        return status

    def _add_account_id(self, account_id: str) -> None:
        if not isinstance(account_id, str) or not account_id.strip():
            raise InvalidOperationError(
                "Номер счёта должен быть непустой строкой."
            )

        normalized_account_id = account_id.strip()

        if normalized_account_id in self._account_ids:
            raise InvalidOperationError(
                "Номер счёта уже добавлен клиенту."
            )

        self._account_ids.append(normalized_account_id)

    def _set_status(self, status: ClientStatus) -> None:
        self._status = self._validate_status(status)
