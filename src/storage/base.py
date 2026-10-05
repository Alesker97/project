"""Общий интерфейс и формат сохраняемой страницы."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any


FIELDS = (
    "url", "title", "text", "links", "metadata",
    "crawled_at", "status_code", "content_type",
)


def prepare_record(data: dict[str, Any]) -> dict[str, Any]:
    """Проверяет запись и приводит дату к строке ISO 8601."""
    if not isinstance(data, dict):
        raise ValueError("Данные страницы должны быть словарём.")
    missing = [field for field in FIELDS if field not in data]
    if missing:
        raise ValueError(f"Отсутствуют поля: {', '.join(missing)}")
    record = {field: data[field] for field in FIELDS}
    for field in ("url", "title", "text", "content_type"):
        if not isinstance(record[field], str):
            raise ValueError(f"{field} должен быть строкой.")
    if not record["url"]:
        raise ValueError("url должен быть непустой строкой.")
    if not isinstance(record["links"], list) or not all(
        isinstance(link, str) for link in record["links"]
    ):
        raise ValueError("links должен быть списком строк.")
    if not isinstance(record["metadata"], dict):
        raise ValueError("metadata должен быть словарём.")
    if isinstance(record["status_code"], bool) or not isinstance(record["status_code"], int):
        raise ValueError("status_code должен быть целым числом.")
    timestamp = record["crawled_at"]
    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        record["crawled_at"] = timestamp.isoformat()
    elif not isinstance(timestamp, str) or not timestamp:
        raise ValueError("crawled_at должен быть datetime или строкой ISO 8601.")
    return record


class DataStorage(ABC):
    @abstractmethod
    async def save(self, data: dict[str, Any]) -> None:
        """Сохраняет одну страницу."""

    async def save_many(self, records: list[dict[str, Any]]) -> None:
        for record in records:
            await self.save(record)

    async def flush(self) -> None:
        """Дожидается записи накопленных данных."""

    @property
    def pending_urls(self) -> list[str]:
        return []

    @abstractmethod
    async def close(self) -> None:
        """Сбрасывает буфер и освобождает ресурсы."""
