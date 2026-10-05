"""Асинхронные хранилища результатов обхода."""

from src.storage.base import DataStorage, prepare_record
from src.storage.csv_storage import CSVStorage
from src.storage.json_storage import JSONStorage
from src.storage.sqlite_storage import SQLiteStorage

__all__ = ["DataStorage", "JSONStorage", "CSVStorage", "SQLiteStorage", "prepare_record"]
