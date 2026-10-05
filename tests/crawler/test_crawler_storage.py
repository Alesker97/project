from collections.abc import AsyncIterator

import pytest
from aiohttp import web

from src.crawler.async_crawler import AsyncCrawler
from src.main import demonstrate_storage
from src.storage import DataStorage, JSONStorage


@pytest.fixture
async def page_site() -> AsyncIterator[str]:
    async def handle(request):
        if request.path == "/":
            body = '<title>Первая</title><a href="/next">Далее</a>'
        else:
            body = "<title>Вторая</title><p>Текст</p>"
        return web.Response(text=body, content_type="text/html")

    app = web.Application()
    app.router.add_get("/{path:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", 0).start()
        yield f"http://127.0.0.1:{runner.addresses[0][1]}"
    finally:
        await runner.cleanup()


async def test_crawler_saves_standard_records(page_site, tmp_path):
    storage = JSONStorage(tmp_path / "crawl.jsonl", buffer_size=2)
    crawler = AsyncCrawler(
        storage=storage, respect_robots=False, requests_per_second=1000,
        max_retries=0,
    )
    try:
        result = await crawler.crawl([page_site], max_pages=2, same_domain_only=True)
        rows = await storage.read_all()
        assert len(result) == 2
        assert len(rows) == 2
        assert crawler.get_storage_stats() == {
            "saved": 2, "failed": 0, "retries": 0, "failed_urls": {},
        }
        root = next(row for row in rows if row["url"] == page_site)
        assert root["title"] == "Первая"
        assert root["links"] == [f"{page_site}/next"]
        assert root["status_code"] == 200
        assert root["content_type"] == "text/html"
        assert root["crawled_at"].endswith("+00:00")
    finally:
        await crawler.close()


async def test_fetch_and_parse_saves_page_without_crawl(page_site, tmp_path):
    storage = JSONStorage(tmp_path / "single.jsonl")
    crawler = AsyncCrawler(
        storage=storage, respect_robots=False,
        requests_per_second=1000, max_retries=0,
    )
    try:
        result = await crawler.fetch_and_parse(page_site)
        assert result["title"] == "Первая"
        assert [row["url"] for row in await storage.read_all()] == [page_site]
        assert crawler.get_storage_stats()["saved"] == 1
    finally:
        await crawler.close()


class FailingStorage(DataStorage):
    def __init__(self, failures: int):
        self.failures = failures
        self.calls = 0
        self.records = []
        self.closed = False

    async def save(self, data):
        self.calls += 1
        if self.calls <= self.failures:
            raise OSError("disk unavailable")
        self.records.append(data)

    async def close(self):
        self.closed = True


class FlushFailingStorage(DataStorage):
    def __init__(self):
        self.pending = []

    async def save(self, data):
        self.pending.append(data["url"])

    @property
    def pending_urls(self):
        return list(self.pending)

    async def flush(self):
        raise OSError("flush unavailable")

    async def close(self):
        pass


async def test_storage_error_retries_without_stopping_crawl(page_site):
    storage = FailingStorage(failures=1)
    crawler = AsyncCrawler(
        storage=storage, storage_retries=2, storage_backoff=0,
        respect_robots=False, requests_per_second=1000, max_retries=0,
    )
    try:
        result = await crawler.crawl([page_site], max_pages=2, same_domain_only=True)
        assert len(result) == 2
        assert len(storage.records) == 2
        assert crawler.get_storage_stats()["saved"] == 2
        assert crawler.get_storage_stats()["retries"] == 1
    finally:
        await crawler.close()
    assert storage.closed


async def test_permanent_storage_error_keeps_page_result(page_site):
    storage = FailingStorage(failures=10)
    crawler = AsyncCrawler(
        storage=storage, storage_retries=1, storage_backoff=0,
        respect_robots=False, requests_per_second=1000, max_retries=0,
    )
    try:
        result = await crawler.crawl([page_site], max_pages=1)
        assert list(result) == [page_site]
        assert crawler.failed_urls == {}
        stats = crawler.get_storage_stats()
        assert stats["saved"] == 0
        assert stats["failed"] == 1
        assert "OSError" in stats["failed_urls"][page_site]
    finally:
        await crawler.close()


async def test_buffer_flush_error_is_reported(page_site):
    crawler = AsyncCrawler(
        storage=FlushFailingStorage(), storage_retries=1,
        storage_backoff=0, respect_robots=False,
        requests_per_second=1000, max_retries=0,
    )
    try:
        assert len(await crawler.crawl([page_site], max_pages=1)) == 1
        stats = crawler.get_storage_stats()
        assert stats["saved"] == 0
        assert stats["failed"] == 1
        assert stats["retries"] == 1
    finally:
        await crawler.close()


async def test_local_demo_writes_and_reads_all_formats(tmp_path):
    results = await demonstrate_storage(tmp_path / "storage_demo")
    assert set(results) == {"JSON Lines", "CSV", "SQLite"}
    for result in results.values():
        assert result["stats"]["saved"] == 2
        assert len(result["pages"]) == 2
