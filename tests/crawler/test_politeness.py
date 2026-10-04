import asyncio
import time
from collections import Counter

import aiohttp
import pytest
from aiohttp import web

from src.crawler.async_crawler import AsyncCrawler
from src.parsers.robots_parser import RobotsParser


@pytest.fixture
async def polite_site():
    config = {
        "robots": "User-agent: TestBot\nDisallow: /private\nCrawl-delay: 0.04\n",
        "robots_status": 200,
        "failures": 2,
        "failure_status": 503,
    }
    requests = []
    hits = Counter()

    async def handle(request):
        requests.append((request.path, time.monotonic(), request.headers.get("User-Agent")))
        hits[request.path] += 1
        if request.path == "/robots.txt":
            return web.Response(text=config["robots"], status=config["robots_status"])
        if request.path == "/redirect":
            raise web.HTTPFound("/private")
        if request.path == "/public-redirect":
            raise web.HTTPFound("/public")
        if request.path == "/loop":
            raise web.HTTPFound("/loop")
        if request.path == "/unstable" and hits[request.path] <= config["failures"]:
            return web.Response(status=config["failure_status"])
        if request.path == "/slow":
            await asyncio.sleep(0.05)
        if request.path == "/missing":
            return web.Response(status=404)
        return web.Response(text=(
            '<h1>Test</h1><a href="/public">Public</a>'
            '<a href="/private">Private</a>'
        ), content_type="text/html")

    app = web.Application()
    app.router.add_get("/{path:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", 0).start()
        yield f"http://127.0.0.1:{runner.addresses[0][1]}", config, requests, hits
    finally:
        await runner.cleanup()


def make_crawler(**options):
    return AsyncCrawler(**{
        "requests_per_second": 1000.0,
        "user_agent": "TestBot/1.0",
        "backoff_factor": 0.02,
        **options,
    })


async def test_blocked_url_never_reaches_server_and_is_logged(polite_site, caplog):
    base, _, requests, hits = polite_site
    crawler = make_crawler()
    try:
        result = await crawler.fetch_url(f"{base}/private")
        assert result == ""
        assert hits["/private"] == 0
        assert hits["/robots.txt"] == 1
        assert "заблокирован robots.txt" in caplog.text
        assert crawler.get_request_stats()["blocked"] == 1
        assert all(agent == "TestBot/1.0" for _, _, agent in requests)
    finally:
        await crawler.close()


async def test_concurrent_requests_obey_crawl_delay_and_share_cache(polite_site):
    base, _, requests, hits = polite_site
    crawler = make_crawler(max_concurrent_per_domain=5)
    try:
        await crawler.fetch_urls([f"{base}/public?i={i}" for i in range(4)])
        assert hits["/robots.txt"] == 1
        starts = [started for _, started, _ in requests]
        assert len(starts) == 5
        assert all(b - a >= 0.035 for a, b in zip(starts, starts[1:]))
        assert crawler.get_request_stats()["average_delay"] >= 0.04
        assert crawler.get_request_stats()["requests"] == 5
    finally:
        await crawler.close()


async def test_min_delay_and_rate_apply_when_robots_disabled(polite_site):
    base, _, requests, hits = polite_site
    crawler = make_crawler(respect_robots=False, requests_per_second=50, min_delay=0.04)
    try:
        await crawler.fetch_urls([f"{base}/private?i={i}" for i in range(3)])
        assert hits["/robots.txt"] == 0
        starts = [started for _, started, _ in requests]
        assert all(b - a >= 0.035 for a, b in zip(starts, starts[1:]))
    finally:
        await crawler.close()


async def test_specific_user_agent_rules_match_http_header(polite_site):
    base, config, requests, hits = polite_site
    config["robots"] = "User-agent: TestBot\nDisallow: /private\n\nUser-agent: *\nDisallow:\n"
    crawler = make_crawler(user_agent="OtherBot/2.0")
    try:
        assert await crawler.fetch_url(f"{base}/private")
        assert hits["/private"] == 1
        assert all(agent == "OtherBot/2.0" for _, _, agent in requests)
    finally:
        await crawler.close()


async def test_redirect_target_is_checked_before_request(polite_site):
    base, _, _, hits = polite_site
    crawler = make_crawler()
    try:
        assert await crawler.fetch_url(f"{base}/redirect") == ""
        assert hits["/redirect"] == 1
        assert hits["/private"] == 0
        assert crawler.get_request_stats()["blocked"] == 1
    finally:
        await crawler.close()


async def test_allowed_redirect_obeys_delay(polite_site):
    base, _, requests, _ = polite_site
    crawler = make_crawler()
    try:
        assert await crawler.fetch_url(f"{base}/public-redirect")
        assert requests[-1][0] == "/public"
        assert requests[-1][1] - requests[-2][1] >= 0.035
    finally:
        await crawler.close()


@pytest.mark.parametrize("status", [429, 503])
async def test_transient_errors_use_exponential_backoff(polite_site, status):
    base, config, requests, hits = polite_site
    config["failure_status"] = status
    crawler = make_crawler(respect_robots=False)
    try:
        assert await crawler.fetch_url(f"{base}/unstable")
        assert hits["/unstable"] == 3
        starts = [started for _, started, _ in requests]
        assert starts[1] - starts[0] >= 0.018
        assert starts[2] - starts[1] >= 0.038
        assert crawler.get_request_stats()["retries"] == 2
        assert crawler.failed_urls == {}
        assert crawler._semaphore_manager.get_stats()["active"] == 0
    finally:
        await crawler.close()


async def test_retry_exhaustion_and_permanent_error(polite_site):
    base, config, _, hits = polite_site
    config["failures"] = 10
    crawler = make_crawler(respect_robots=False, max_retries=1)
    try:
        assert await crawler.fetch_url(f"{base}/unstable") == ""
        assert crawler.failed_urls[f"{base}/unstable"] == "HTTP 503"
        assert hits["/unstable"] == 2
        assert await crawler.fetch_url(f"{base}/missing") == ""
        assert hits["/missing"] == 1
    finally:
        await crawler.close()


async def test_timeouts_are_retried_and_resources_released(polite_site):
    base, _, _, hits = polite_site
    crawler = make_crawler(respect_robots=False, max_retries=1)
    crawler._timeout = aiohttp.ClientTimeout(total=0.02)
    try:
        assert await crawler.fetch_url(f"{base}/slow") == ""
        assert hits["/slow"] == 2
        assert crawler.get_request_stats()["retries"] == 1
        assert crawler._semaphore_manager.get_stats()["active"] == 0
    finally:
        await crawler.close()


async def test_unavailable_robots_blocks_pages_after_retries(polite_site):
    base, config, _, hits = polite_site
    config["robots_status"] = 503
    crawler = make_crawler(max_retries=1)
    try:
        assert await crawler.fetch_url(f"{base}/public") == ""
        assert hits["/robots.txt"] == 2
        assert hits["/public"] == 0
    finally:
        await crawler.close()


async def test_crawl_stats_and_reset(polite_site, capsys):
    base, _, _, hits = polite_site
    crawler = make_crawler()
    try:
        results = await crawler.crawl([base], same_domain_only=True)
        assert len(results) == 2
        stats = crawler.get_crawl_stats()
        assert stats["blocked"] == 1
        assert stats["failed"] == 1
        assert stats["successful"] == 2
        assert stats["processed"] == 3
        assert stats["requests"] == 3
        assert stats["average_delay"] >= 0.04
        output = capsys.readouterr().out
        assert "req/sec" in output
        assert "Средняя задержка:" in output
        assert "Блокировок robots.txt:" in output
        await crawler.crawl([f"{base}/public"], max_pages=1)
        assert crawler.get_request_stats()["blocked"] == 0
        assert crawler.get_request_stats()["requests"] == 1
        assert hits["/robots.txt"] == 1
    finally:
        await crawler.close()


async def test_standalone_robots_parser_owns_and_closes_session(polite_site):
    base, _, _, _ = polite_site
    parser = RobotsParser(user_agent="TestBot/1.0")
    try:
        await parser.fetch_robots(base)
        assert parser.can_fetch(f"{base}/public", "TestBot")
        assert not parser.can_fetch(f"{base}/private", "TestBot")
        session = parser._session
    finally:
        await parser.close()
    assert session.closed


@pytest.mark.parametrize("options", [
    {"user_agent": ""}, {"user_agent": "bot\ninvalid"},
    {"respect_robots": 1}, {"max_retries": -1}, {"max_retries": True},
    {"backoff_factor": -1}, {"max_backoff": float("inf")},
])
def test_invalid_politeness_options(options):
    with pytest.raises(ValueError):
        AsyncCrawler(**options)
