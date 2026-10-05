import asyncio
from collections import Counter

import pytest
import aiohttp
from aiohttp import web

from src.crawler.async_crawler import AsyncCrawler
from src.crawler.errors import ParseError, PermanentError, TransientError
from src.crawler.retry_strategy import RetryStrategy


@pytest.fixture
async def error_site():
    hits = Counter()

    async def handle(request):
        path = request.path
        hits[path] += 1
        if path == "/unavailable" and hits[path] <= 2:
            return web.Response(status=503)
        if path == "/limited" and hits[path] <= 1:
            return web.Response(status=429)
        if path == "/missing":
            return web.Response(status=404)
        if path == "/server-error":
            return web.Response(status=500)
        if path == "/slow":
            await asyncio.sleep(0.026)
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/{path:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", 0).start()
        yield f"http://127.0.0.1:{runner.addresses[0][1]}", hits
    finally:
        await runner.cleanup()


async def test_http_classification_stats_and_report(error_site):
    base, hits = error_site
    crawler = AsyncCrawler(
        respect_robots=False, requests_per_second=1000,
        max_retries=2, backoff_factor=0.001,
    )
    try:
        assert await crawler.fetch_url(f"{base}/unavailable") == "ok"
        assert await crawler.fetch_url(f"{base}/limited") == "ok"
        assert await crawler.fetch_url(f"{base}/missing") == ""
        assert await crawler.fetch_url(f"{base}/server-error") == ""
        assert hits["/unavailable"] == 3
        assert hits["/limited"] == 2
        assert hits["/missing"] == 1
        assert hits["/server-error"] == 3
        stats = crawler.get_error_stats()
        assert stats["errors_by_type"] == {"TransientError": 6, "PermanentError": 1}
        assert stats["successful_retries"] == 2
        assert stats["retries"] == 5
        assert stats["average_retry_time"] > 0
        assert stats["permanent_urls"] == [f"{base}/missing"]
        report = crawler.get_error_report()
        assert report["failed_urls"][f"{base}/missing"] == "HTTP 404"
        assert report["attempts"][-1]["result"] == "failed"
    finally:
        await crawler.close()


async def test_timeout_grows_on_retry(error_site, monkeypatch):
    base, hits = error_site
    observed_timeouts = []
    original_get = aiohttp.ClientSession.get

    def capture_get(self, *args, **kwargs):
        observed_timeouts.append(kwargs["timeout"].total)
        return original_get(self, *args, **kwargs)

    monkeypatch.setattr(aiohttp.ClientSession, "get", capture_get)
    crawler = AsyncCrawler(
        respect_robots=False, requests_per_second=1000,
        max_retries=2, backoff_factor=0.001,
        total_timeout=0.02,
    )
    try:
        assert await crawler.fetch_url(f"{base}/slow") == "ok"
        assert hits["/slow"] in {2, 3}
        assert observed_timeouts[:2] == pytest.approx([0.02, 0.03])
        assert crawler.get_error_stats()["successful_retries"] == 1
    finally:
        await crawler.close()


async def test_external_strategy_uses_single_attempt_fetch(error_site):
    base, hits = error_site
    crawler = AsyncCrawler(
        respect_robots=False, requests_per_second=1000,
        backoff_factor=0.001,
    )
    strategy = RetryStrategy(max_retries=2, backoff_factor=0.001)
    try:
        assert await strategy.execute_with_retry(
            crawler.fetch_url, f"{base}/unavailable", raise_on_error=True,
        ) == "ok"
        assert hits["/unavailable"] == 3
        assert strategy.get_stats()["retries"] == 2
        assert crawler.get_error_stats()["retries"] == 0
        with pytest.raises(PermanentError):
            await crawler.fetch_url(f"{base}/missing", raise_on_error=True)
        with pytest.raises(TransientError):
            await crawler.fetch_url(f"{base}/server-error", raise_on_error=True)
    finally:
        await crawler.close()


async def test_parse_error_is_recorded(error_site, monkeypatch):
    base, _ = error_site
    crawler = AsyncCrawler(respect_robots=False, requests_per_second=1000)

    async def broken_parser(html, url):
        raise RuntimeError("broken HTML parser")

    monkeypatch.setattr(crawler._parser, "parse_html", broken_parser)
    try:
        with pytest.raises(ParseError):
            await crawler.fetch_and_parse(f"{base}/ok")
        assert crawler.get_error_stats()["errors_by_type"]["ParseError"] == 1
        assert crawler.get_error_report()["attempts"][-1]["result"] == "failed"
    finally:
        await crawler.close()
