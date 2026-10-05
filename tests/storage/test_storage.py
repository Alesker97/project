import asyncio
import json
from datetime import datetime, timezone

import aiosqlite
import pytest

from src.storage import CSVStorage, JSONStorage, SQLiteStorage


def page(number: int) -> dict[str, object]:
    return {
        "url": f"https://example.test/{number}",
        "title": f"Заголовок, {number}",
        "text": 'Текст с кавычками " и переносом\nстроки',
        "links": ["https://example.test/next?a=1,b=2"],
        "metadata": {"description": "Описание; тест"},
        "crawled_at": datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
        "status_code": 200,
        "content_type": "text/html",
    }


async def test_json_lines_round_trip_and_append(tmp_path):
    path = tmp_path / "nested" / "pages.jsonl"
    storage = JSONStorage(path, buffer_size=10)
    try:
        await asyncio.gather(*(storage.save(page(index)) for index in range(25)))
        assert storage.saved_count == 20
        assert len(storage.pending_urls) == 5
        rows = await storage.read_all()
        assert len(rows) == 25
        assert rows[0]["crawled_at"] == "2026-01-02T03:04:00+00:00"
        assert rows[0]["links"] == page(0)["links"]
    finally:
        await storage.close()
    assert len(path.read_text(encoding="utf-8").splitlines()) == 25

    reopened = JSONStorage(path)
    try:
        await reopened.save(page(25))
        assert len(await reopened.read_all()) == 26
    finally:
        await reopened.close()


async def test_pretty_json_is_valid_array_after_each_save(tmp_path):
    path = tmp_path / "pages.json"
    storage = JSONStorage(path, json_lines=False, indent=2)
    try:
        await storage.save(page(1))
        assert len(json.loads(path.read_text(encoding="utf-8"))) == 1
        await storage.save(page(2))
        rows = json.loads(path.read_text(encoding="utf-8"))
        assert len(rows) == 2
        assert "\n  \"url\"" in path.read_text(encoding="utf-8")
    finally:
        await storage.close()


async def test_csv_round_trip_escapes_special_characters(tmp_path):
    path = tmp_path / "pages.csv"
    storage = CSVStorage(path, encoding="utf-8", buffer_size=2)
    try:
        await storage.save(page(1))
        await storage.save(page(2))
        rows = await storage.read_all()
        assert len(rows) == 2
        assert rows[0]["text"] == page(1)["text"]
        assert rows[0]["metadata"] == page(1)["metadata"]
        assert rows[0]["links"] == page(1)["links"]
        assert rows[0]["status_code"] == 200
    finally:
        await storage.close()

    reopened = CSVStorage(path)
    try:
        await reopened.save(page(3))
        assert len(await reopened.read_all()) == 3
    finally:
        await reopened.close()


async def test_csv_supports_configured_encoding(tmp_path):
    path = tmp_path / "pages-cp1251.csv"
    storage = CSVStorage(path, encoding="cp1251")
    try:
        await storage.save(page(1))
        assert (await storage.read_all())[0]["title"] == "Заголовок, 1"
    finally:
        await storage.close()
    assert "Заголовок" in path.read_text(encoding="cp1251")


async def test_sqlite_batch_round_trip_indexes_and_upsert(tmp_path):
    path = tmp_path / "nested" / "pages.db"
    storage = SQLiteStorage(path, batch_size=3)
    try:
        await storage.init_db()
        await storage.save_many([page(1), page(2)])
        assert storage.saved_count == 0
        await storage.save(page(3))
        assert storage.saved_count == 3
        updated = page(1)
        updated["title"] = "Обновлённый заголовок"
        await storage.save(updated)
        rows = await storage.read_all()
        assert len(rows) == 3
        assert rows[0]["title"] == "Обновлённый заголовок"
        assert rows[0]["links"] == page(1)["links"]
        assert rows[0]["metadata"] == page(1)["metadata"]
        async with aiosqlite.connect(path) as db:
            cursor = await db.execute("PRAGMA index_list(pages)")
            indexes = {row[1] for row in await cursor.fetchall()}
            await cursor.close()
        assert {"idx_pages_crawled_at", "idx_pages_status_code"} <= indexes
    finally:
        await storage.close()

    reopened = SQLiteStorage(path)
    try:
        assert len(await reopened.read_all()) == 3
    finally:
        await reopened.close()


@pytest.mark.parametrize("storage_type", [JSONStorage, CSVStorage, SQLiteStorage])
async def test_invalid_record_is_rejected(tmp_path, storage_type):
    storage = storage_type(tmp_path / "invalid")
    try:
        with pytest.raises(ValueError, match="Отсутствуют поля"):
            await storage.save({"url": "https://example.test"})
    finally:
        await storage.close()
