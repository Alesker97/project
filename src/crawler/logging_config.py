"""Настройка JSON-логов в консоли и ротируемом файле."""

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            event["exception"] = self.formatException(record.exc_info)
        for field in ("url", "attempt", "status_code"):
            if hasattr(record, field):
                event[field] = getattr(record, field)
        return json.dumps(event, ensure_ascii=False)


def configure_logging(
    path: str | Path,
    *,
    level: str = "INFO",
    max_bytes: int = 1_000_000,
    backup_count: int = 3,
) -> None:
    name = level.upper()
    if name not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        raise ValueError("Уровень логирования должен быть DEBUG, INFO, WARNING или ERROR.")
    if (
        isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0
        or isinstance(backup_count, bool) or not isinstance(backup_count, int) or backup_count < 0
    ):
        raise ValueError("Параметры ротации логов должны быть неотрицательными.")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    formatter = JSONFormatter()
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        destination, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_crawler_managed", False):
            root.removeHandler(handler)
            handler.close()
    stream._crawler_managed = True
    file_handler._crawler_managed = True
    root.addHandler(stream)
    root.addHandler(file_handler)
    root.setLevel(getattr(logging, name))
