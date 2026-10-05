"""Асинхронная запись CSV с экранированием через стандартный csv."""

import asyncio
import csv
import io
import json
from pathlib import Path
from typing import Any

import aiofiles

from src.storage.base import DataStorage, prepare_record


class CSVStorage(DataStorage):
    def __init__(
        self,
        path: str | Path,
        *,
        encoding: str = "utf-8",
        buffer_size: int = 1,
    ) -> None:
        if isinstance(buffer_size, bool) or not isinstance(buffer_size, int) or buffer_size <= 0:
            raise ValueError("buffer_size должен быть положительным целым числом.")
        self.path = Path(path)
        self.encoding = encoding
        self.buffer_size = buffer_size
        self._buffer: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._closed = False
        self._headers: list[str] | None = None
        self.saved_count = 0

    async def save(self, data: dict[str, Any]) -> None:
        record = prepare_record(data)
        async with self._lock:
            if self._closed:
                raise RuntimeError("CSVStorage закрыт.")
            self._buffer.append(record)
            if len(self._buffer) >= self.buffer_size:
                try:
                    await self._flush_locked()
                except Exception:
                    self._buffer.pop()
                    raise

    @property
    def pending_urls(self) -> list[str]:
        return [record["url"] for record in self._buffer]

    async def flush(self) -> None:
        async with self._lock:
            await self._flush_locked()

    async def _flush_locked(self) -> None:
        if not self._buffer:
            return
        await asyncio.to_thread(self.path.parent.mkdir, parents=True, exist_ok=True)
        exists = await asyncio.to_thread(self.path.exists)
        if self._headers is None and exists:
            async with aiofiles.open(self.path, "r", encoding=self.encoding, newline="") as file:
                first_line = await file.readline()
            if first_line:
                self._headers = next(csv.reader([first_line]))
        write_header = self._headers is None
        headers = list(self._buffer[0]) if write_header else self._headers
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n")
        if write_header:
            writer.writeheader()
        for record in self._buffer:
            row = dict(record)
            row["links"] = json.dumps(row["links"], ensure_ascii=False)
            row["metadata"] = json.dumps(row["metadata"], ensure_ascii=False)
            writer.writerow(row)
        async with aiofiles.open(self.path, "a", encoding=self.encoding, newline="") as file:
            await file.write(output.getvalue())
        self._headers = headers
        self.saved_count += len(self._buffer)
        self._buffer.clear()

    async def read_all(self) -> list[dict[str, Any]]:
        await self.flush()
        if not await asyncio.to_thread(self.path.exists):
            return []
        async with aiofiles.open(self.path, "r", encoding=self.encoding, newline="") as file:
            content = await file.read()
        rows = list(csv.DictReader(io.StringIO(content, newline="")))
        for row in rows:
            row["links"] = json.loads(row["links"])
            row["metadata"] = json.loads(row["metadata"])
            row["status_code"] = int(row["status_code"])
        return rows

    async def close(self) -> None:
        async with self._lock:
            if not self._closed:
                await self._flush_locked()
                self._closed = True
