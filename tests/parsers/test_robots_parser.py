import asyncio

import aiohttp
import pytest

from src.parsers.robots_parser import RobotsParser


async def test_rules_for_specific_user_agent_and_fractional_delay():
    async def fetch(url):
        return 200, (
            "User-agent: TestBot\nDisallow: /private\nCrawl-delay: 0.25\n\n"
            "User-agent: *\nDisallow: /other\nCrawl-delay: 2\n"
        ), None

    parser = RobotsParser(fetcher=fetch)
    assert not parser.can_fetch("https://example.com/public")
    await parser.fetch_robots("https://example.com/page")
    assert not parser.can_fetch("https://example.com/private", "TestBot/1.0")
    assert parser.can_fetch("https://example.com/other", "TestBot/1.0")
    assert not parser.can_fetch("https://example.com/other", "OtherBot")
    assert parser.get_crawl_delay("TestBot/1.0") == 0.25
    assert parser.get_crawl_delay("OtherBot") == 2.0


async def test_concurrent_loads_use_one_cached_request_per_origin():
    calls = []

    async def fetch(url):
        calls.append(url)
        await asyncio.sleep(0)
        return 200, "User-agent: *\nDisallow: /private", None

    parser = RobotsParser(fetcher=fetch)
    await asyncio.gather(*(parser.fetch_robots("https://EXAMPLE.com:443/path") for _ in range(5)))
    await parser.fetch_robots("https://example.com/other")
    await parser.fetch_robots("http://example.com/path")
    await parser.fetch_robots("https://example.com:8080/path")
    assert calls == [
        "https://example.com/robots.txt",
        "http://example.com/robots.txt",
        "https://example.com:8080/robots.txt",
    ]


async def test_delay_lookup_is_explicit_for_concurrent_domains():
    async def fetch(url):
        delay = 1 if "first" in url else 2
        return 200, f"User-agent: *\nCrawl-delay: {delay}", None

    parser = RobotsParser(fetcher=fetch)
    await asyncio.gather(
        parser.fetch_robots("https://first.example"),
        parser.fetch_robots("https://second.example"),
    )
    assert parser.get_crawl_delay(url="https://first.example/page") == 1
    assert parser.get_crawl_delay(url="https://second.example/page") == 2


@pytest.mark.parametrize("status, allowed", [(404, True), (403, False), (429, False), (503, False)])
async def test_robots_http_error_policy(status, allowed):
    async def fetch(url):
        return status, "", None

    parser = RobotsParser(fetcher=fetch)
    result = await parser.fetch_robots("https://example.com")
    assert result["status"] == status
    assert parser.can_fetch("https://example.com/page") is allowed


async def test_network_error_blocks_crawl():
    async def fetch(url):
        raise aiohttp.ClientConnectionError("offline")

    parser = RobotsParser(fetcher=fetch)
    await parser.fetch_robots("https://example.com")
    assert not parser.can_fetch("https://example.com/page")


async def test_robots_redirect_keeps_rules_for_original_origin():
    calls = []

    async def fetch(url):
        calls.append(url)
        if len(calls) == 1:
            return 302, "", "https://rules.example/robots.txt"
        return 200, "User-agent: *\nDisallow: /private", None

    parser = RobotsParser(fetcher=fetch)
    await parser.fetch_robots("https://example.com")
    assert len(calls) == 2
    assert not parser.can_fetch("https://example.com/private")
    assert parser.can_fetch("https://example.com/public")


async def test_invalid_delay_is_ignored_and_allow_is_parsed():
    async def fetch(url):
        return 200, (
            "User-agent: *\nAllow: /private/public\nDisallow: /private\nCrawl-delay: nan"
        ), None

    parser = RobotsParser(fetcher=fetch)
    await parser.fetch_robots("https://example.com")
    assert parser.get_crawl_delay() == 0
    assert parser.can_fetch("https://example.com/private/public")
    assert not parser.can_fetch("https://example.com/private/secret")
