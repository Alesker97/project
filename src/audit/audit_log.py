from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from enum import Enum
import json
from pathlib import Path

from src.enums.audit_level import AuditLevel
from src.exceptions import InvalidOperationError


class AuditLog:
    def __init__(
        self,
        file_path: str | Path | None = None,
        time_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._file_path = self._validate_file_path(file_path)
        if time_provider is not None and not callable(time_provider):
            raise InvalidOperationError(
                "Источник времени должен быть вызываемым объектом."
            )
        self._time_provider = time_provider or datetime.now
        self._entries: list[dict[str, object]] = []

    @property
    def file_path(self) -> Path | None:
        return self._file_path

    @property
    def entries(self) -> list[dict[str, object]]:
        return deepcopy(self._entries)

    def log(
        self,
        level: AuditLevel,
        event_type: str,
        message: str,
        client_id: str | None = None,
        transaction_id: str | None = None,
        details: dict[str, object] | None = None,
        timestamp: datetime | None = None,
    ) -> dict[str, object]:
        validated_level = self._validate_level(level)
        validated_event_type = self._validate_required_text(
            event_type,
            "Тип события",
        )
        validated_message = self._validate_required_text(
            message,
            "Сообщение",
        )
        validated_client_id = self._validate_optional_text(
            client_id,
            "ID клиента",
        )
        validated_transaction_id = self._validate_optional_text(
            transaction_id,
            "ID транзакции",
        )
        validated_details = self._validate_details(details)
        validated_timestamp = self._validate_timestamp(
            timestamp or self._get_current_time()
        )

        entry: dict[str, object] = {
            "timestamp": validated_timestamp,
            "level": validated_level,
            "event_type": validated_event_type,
            "message": validated_message,
            "client_id": validated_client_id,
            "transaction_id": validated_transaction_id,
            "details": validated_details,
        }

        if self._file_path is not None:
            self._write_to_file(entry)

        self._entries.append(entry)
        return deepcopy(entry)

    def filter(
        self,
        level: AuditLevel | None = None,
        event_type: str | None = None,
        client_id: str | None = None,
        transaction_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, object]]:
        if level is not None:
            self._validate_level(level)

        event_type = self._validate_optional_text(
            event_type,
            "Тип события",
        )
        client_id = self._validate_optional_text(
            client_id,
            "ID клиента",
        )
        transaction_id = self._validate_optional_text(
            transaction_id,
            "ID транзакции",
        )

        if start_time is not None:
            self._validate_timestamp(start_time)
        if end_time is not None:
            self._validate_timestamp(end_time)
        if (
            start_time is not None
            and end_time is not None
            and start_time > end_time
        ):
            raise InvalidOperationError(
                "Начальное время не может быть позже конечного."
            )

        entries = self._entries

        if level is not None:
            entries = [
                entry
                for entry in entries
                if entry["level"] is level
            ]
        if event_type is not None:
            entries = [
                entry
                for entry in entries
                if entry["event_type"] == event_type
            ]
        if client_id is not None:
            entries = [
                entry
                for entry in entries
                if entry["client_id"] == client_id
            ]
        if transaction_id is not None:
            entries = [
                entry
                for entry in entries
                if entry["transaction_id"] == transaction_id
            ]
        if start_time is not None:
            entries = [
                entry
                for entry in entries
                if entry["timestamp"] >= start_time
            ]
        if end_time is not None:
            entries = [
                entry
                for entry in entries
                if entry["timestamp"] <= end_time
            ]

        return deepcopy(entries)

    def __len__(self) -> int:
        return len(self._entries)

    def _write_to_file(
        self,
        entry: dict[str, object],
    ) -> None:
        if self._file_path is None:
            return

        try:
            self._file_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            serialized_entry = self._make_json_compatible(entry)
            serialized_line = json.dumps(
                serialized_entry,
                ensure_ascii=False,
                allow_nan=False,
            )
            with self._file_path.open(
                "a",
                encoding="utf-8",
            ) as audit_file:
                audit_file.write(f"{serialized_line}\n")
        except (OSError, TypeError, ValueError) as error:
            raise InvalidOperationError(
                "Не удалось сохранить запись аудита в файл."
            ) from error

    def _get_current_time(self) -> datetime:
        current_time = self._time_provider()
        return self._validate_timestamp(current_time)

    @staticmethod
    def _validate_file_path(
        file_path: str | Path | None,
    ) -> Path | None:
        if file_path is None:
            return None
        if isinstance(file_path, Path):
            return file_path
        if isinstance(file_path, str):
            file_path = file_path.strip()
            if file_path:
                return Path(file_path)
        raise InvalidOperationError(
            "Путь к журналу аудита указан некорректно."
        )

    @staticmethod
    def _validate_level(level: AuditLevel) -> AuditLevel:
        if not isinstance(level, AuditLevel):
            raise InvalidOperationError(
                "Указан недопустимый уровень аудита."
            )
        return level

    @staticmethod
    def _validate_required_text(
        value: str,
        field_name: str,
    ) -> str:
        if not isinstance(value, str) or not value.strip():
            raise InvalidOperationError(
                f"{field_name} не может быть пустым."
            )
        return value.strip()

    @staticmethod
    def _validate_optional_text(
        value: str | None,
        field_name: str,
    ) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise InvalidOperationError(
                f"{field_name} указан некорректно."
            )
        return value.strip()

    @staticmethod
    def _validate_timestamp(timestamp: datetime) -> datetime:
        if not isinstance(timestamp, datetime):
            raise InvalidOperationError(
                "Время записи должно иметь тип datetime."
            )
        return timestamp

    @staticmethod
    def _validate_details(
        details: dict[str, object] | None,
    ) -> dict[str, object]:
        if details is None:
            return {}
        if not isinstance(details, dict):
            raise InvalidOperationError(
                "Дополнительные данные должны быть словарём."
            )
        if not all(
            isinstance(key, str)
            for key in details
        ):
            raise InvalidOperationError(
                "Ключи дополнительных данных должны быть строками."
            )

        validated_details = deepcopy(details)
        AuditLog._make_json_compatible(validated_details)
        return validated_details

    @staticmethod
    def _make_json_compatible(value: object) -> object:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {
                key: AuditLog._make_json_compatible(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [
                AuditLog._make_json_compatible(item)
                for item in value
            ]
        if (
            value is None
            or isinstance(value, (str, int, float, bool))
        ):
            return value
        raise InvalidOperationError(
            "Дополнительные данные содержат "
            "неподдерживаемое значение."
        )
