"""Асинхронная запись JSON Lines или форматированного массива JSON."""

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any

import aiofiles

from src.storage.base import DataStorage, prepare_record


class JSONStorage(DataStorage):
    def __init__(
        self,
        path: str | Path,
        *,
        json_lines: bool = True,
        indent: int = 2,
        encoding: str = "utf-8",
        buffer_size: int = 1,
    ) -> None:
        if isinstance(buffer_size, bool) or not isinstance(buffer_size, int) or buffer_size <= 0:
            raise ValueError("buffer_size должен быть положительным целым числом.")
        if isinstance(indent, bool) or not isinstance(indent, int) or indent < 0:
            raise ValueError("indent должен быть неотрицательным целым числом.")
        self.path = Path(path)
        self.json_lines = json_lines
        self.indent = indent
        self.encoding = encoding
        self.buffer_size = buffer_size
        self._buffer: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._closed = False
        self.saved_count = 0

    async def save(self, data: dict[str, Any]) -> None:
        record = prepare_record(data)
        async with self._lock:
            if self._closed:
                raise RuntimeError("JSONStorage закрыт.")
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
        if self.json_lines:
            payload = "".join(
                json.dumps(record, ensure_ascii=False) + "\n"
                for record in self._buffer
            )
            async with aiofiles.open(self.path, "a", encoding=self.encoding) as file:
                await file.write(payload)
        else:
            exists = await asyncio.to_thread(self.path.exists)
            if exists:
                async with aiofiles.open(self.path, "r", encoding=self.encoding) as file:
                    current = await file.read()
                current = current.rstrip()
                if not current.startswith("[") or not current.endswith("]"):
                    raise ValueError("Существующий файл не является массивом JSON.")
                prefix = current[:-1].rstrip()
                has_records = prefix != "["
            else:
                prefix, has_records = "[", False
            entries = ",\n".join(
                json.dumps(record, ensure_ascii=False, indent=self.indent)
                for record in self._buffer
            )
            payload = prefix + (",\n" if has_records else "\n") + entries + "\n]\n"
            temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
            try:
                async with aiofiles.open(temporary, "w", encoding=self.encoding) as file:
                    await file.write(payload)
                await asyncio.to_thread(os.replace, temporary, self.path)
            finally:
                await asyncio.to_thread(temporary.unlink, missing_ok=True)
        self.saved_count += len(self._buffer)
        self._buffer.clear()

    async def read_all(self) -> list[dict[str, Any]]:
        await self.flush()
        if not await asyncio.to_thread(self.path.exists):
            return []
        async with aiofiles.open(self.path, "r", encoding=self.encoding) as file:
            content = await file.read()
        if self.json_lines:
            return [json.loads(line) for line in content.splitlines() if line.strip()]
        return json.loads(content)

    async def close(self) -> None:
        async with self._lock:
            if not self._closed:
                await self._flush_locked()
                self._closed = True
