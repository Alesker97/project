"""Асинхронное SQLite-хранилище страниц с пакетной вставкой."""

import asyncio
import json
from pathlib import Path
from typing import Any

import aiosqlite

from src.storage.base import DataStorage, prepare_record


class SQLiteStorage(DataStorage):
    def __init__(self, path: str | Path, *, batch_size: int = 1) -> None:
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError("batch_size должен быть положительным целым числом.")
        self.path = Path(path)
        self.batch_size = batch_size
        self._db: aiosqlite.Connection | None = None
        self._buffer: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._closed = False
        self.saved_count = 0

    async def init_db(self) -> None:
        async with self._lock:
            await self._init_locked()

    async def _init_locked(self) -> None:
        if self._closed:
            raise RuntimeError("SQLiteStorage закрыт.")
        if self._db is not None:
            return
        await asyncio.to_thread(self.path.parent.mkdir, parents=True, exist_ok=True)
        db = await aiosqlite.connect(self.path)
        try:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS pages (
                    url TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    links TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    crawled_at TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    content_type TEXT NOT NULL
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_pages_crawled_at ON pages(crawled_at)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_pages_status_code ON pages(status_code)")
            await db.commit()
        except Exception:
            await db.close()
            raise
        self._db = db

    async def save(self, data: dict[str, Any]) -> None:
        record = prepare_record(data)
        async with self._lock:
            await self._init_locked()
            self._buffer.append(record)
            if len(self._buffer) >= self.batch_size:
                try:
                    await self._flush_locked()
                except Exception:
                    self._buffer.pop()
                    raise

    @property
    def pending_urls(self) -> list[str]:
        return [record["url"] for record in self._buffer]

    async def save_many(self, records: list[dict[str, Any]]) -> None:
        prepared = [prepare_record(record) for record in records]
        async with self._lock:
            await self._init_locked()
            previous_count = len(self._buffer)
            self._buffer.extend(prepared)
            if len(self._buffer) >= self.batch_size:
                try:
                    await self._flush_locked()
                except Exception:
                    del self._buffer[previous_count:]
                    raise

    async def flush(self) -> None:
        async with self._lock:
            await self._flush_locked()

    async def _flush_locked(self) -> None:
        if not self._buffer:
            return
        assert self._db is not None
        rows = [(
            record["url"], record["title"], record["text"],
            json.dumps(record["links"], ensure_ascii=False),
            json.dumps(record["metadata"], ensure_ascii=False),
            record["crawled_at"], record["status_code"], record["content_type"],
        ) for record in self._buffer]
        try:
            await self._db.executemany(
                """INSERT INTO pages
                (url, title, text, links, metadata, crawled_at, status_code, content_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title=excluded.title, text=excluded.text, links=excluded.links,
                    metadata=excluded.metadata, crawled_at=excluded.crawled_at,
                    status_code=excluded.status_code, content_type=excluded.content_type""",
                rows,
            )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        self.saved_count += len(self._buffer)
        self._buffer.clear()

    async def read_all(self) -> list[dict[str, Any]]:
        async with self._lock:
            await self._init_locked()
            await self._flush_locked()
            assert self._db is not None
            cursor = await self._db.execute(
                "SELECT url, title, text, links, metadata, crawled_at, status_code, content_type FROM pages ORDER BY url"
            )
            try:
                rows = await cursor.fetchall()
            finally:
                await cursor.close()
        return [{
            "url": row[0], "title": row[1], "text": row[2],
            "links": json.loads(row[3]), "metadata": json.loads(row[4]),
            "crawled_at": row[5], "status_code": row[6], "content_type": row[7],
        } for row in rows]

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            await self._flush_locked()
            if self._db is not None:
                await self._db.close()
                self._db = None
            self._closed = True
