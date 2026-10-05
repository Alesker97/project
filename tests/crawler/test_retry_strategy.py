import asyncio

import pytest

from src.crawler.errors import NetworkError, PermanentError, TransientError
from src.crawler.retry_strategy import RetryStrategy, retry_attempt


async def test_transient_errors_retry_with_exponential_backoff(monkeypatch):
    waits = []

    async def fake_sleep(delay):
        waits.append(delay)

    monkeypatch.setattr("src.crawler.retry_strategy.asyncio.sleep", fake_sleep)
    attempts = []

    async def flaky(url):
        attempts.append(retry_attempt.get())
        if len(attempts) < 3:
            raise TransientError("HTTP 503", url=url, status=503)
        return "ok"

    strategy = RetryStrategy(max_retries=3, backoff_factor=0.5)
    assert await strategy.execute_with_retry(flaky, "https://example.test") == "ok"
    assert attempts == [0, 1, 2]
    assert waits == [0.5, 1.0]
    assert strategy.get_stats()["successful_retries"] == 1
    assert strategy.get_stats()["errors_by_type"] == {"TransientError": 2}


async def test_permanent_error_is_not_retried():
    calls = 0

    async def missing(url):
        nonlocal calls
        calls += 1
        raise PermanentError("HTTP 404", url=url, status=404)

    strategy = RetryStrategy()
    with pytest.raises(PermanentError):
        await strategy.execute_with_retry(missing, "https://example.test/missing")
    assert calls == 1
    assert strategy.get_stats()["retries"] == 0
    assert strategy.get_stats()["permanent_urls"] == ["https://example.test/missing"]


async def test_type_limits_and_429_delay(monkeypatch):
    waits = []

    async def fake_sleep(delay):
        waits.append(delay)

    monkeypatch.setattr("src.crawler.retry_strategy.asyncio.sleep", fake_sleep)
    calls = 0

    async def limited(url):
        nonlocal calls
        calls += 1
        raise TransientError("HTTP 429", url=url, status=429)

    strategy = RetryStrategy(
        max_retries=4,
        backoff_factor=0.25,
        retries_by_type={TransientError: 2},
    )
    with pytest.raises(TransientError):
        await strategy.execute_with_retry(limited, "https://example.test")
    assert calls == 3
    assert waits == [0.5, 1.0]
    assert strategy.get_stats()["retries"] == 2


async def test_http_500_has_two_retry_limit(monkeypatch):
    async def fake_sleep(delay):
        pass

    monkeypatch.setattr("src.crawler.retry_strategy.asyncio.sleep", fake_sleep)
    calls = 0

    async def server_error(url):
        nonlocal calls
        calls += 1
        raise TransientError("HTTP 500", url=url, status=500)

    strategy = RetryStrategy(max_retries=5, backoff_factor=0)
    with pytest.raises(TransientError):
        await strategy.execute_with_retry(server_error, "https://example.test")
    assert calls == 3


async def test_network_error_retries_and_custom_types_do_not(monkeypatch):
    async def fake_sleep(delay):
        pass

    monkeypatch.setattr("src.crawler.retry_strategy.asyncio.sleep", fake_sleep)
    calls = 0

    async def offline():
        nonlocal calls
        calls += 1
        raise NetworkError("DNS")

    strategy = RetryStrategy(max_retries=1)
    with pytest.raises(NetworkError):
        await strategy.execute_with_retry(offline)
    assert calls == 2

    strategy = RetryStrategy(max_retries=3, retry_on=[TransientError])
    with pytest.raises(NetworkError):
        await strategy.execute_with_retry(offline)
    assert calls == 3


async def test_raw_timeout_is_classified_and_retried(monkeypatch):
    waits = []

    async def fake_sleep(delay):
        waits.append(delay)

    monkeypatch.setattr("src.crawler.retry_strategy.asyncio.sleep", fake_sleep)
    calls = 0

    async def timeout(url):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise asyncio.TimeoutError()
        return "ready"

    strategy = RetryStrategy(
        max_retries=1,
        backoff_factor=0.1,
        backoff_by_type={TransientError: 3.0},
    )
    assert await strategy.execute_with_retry(timeout, "https://example.test") == "ready"
    assert waits == [pytest.approx(0.3)]
    assert strategy.get_stats()["errors_by_type"] == {"TransientError": 1}


async def test_cancellation_is_not_counted():
    async def cancelled():
        raise asyncio.CancelledError()

    strategy = RetryStrategy()
    with pytest.raises(asyncio.CancelledError):
        await strategy.execute_with_retry(cancelled)
    assert strategy.get_stats()["errors_by_type"] == {}
