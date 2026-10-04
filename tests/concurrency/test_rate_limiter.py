import asyncio
import time
from types import SimpleNamespace

import pytest

from src.concurrency import rate_limiter as limiter_module
from src.concurrency.rate_limiter import RateLimiter


@pytest.fixture
def fake_clock(monkeypatch):
    state = SimpleNamespace(now=0.0, waits=[])

    async def sleep(delay):
        state.waits.append(delay)
        state.now += delay

    monkeypatch.setattr(limiter_module, "time", SimpleNamespace(monotonic=lambda: state.now))
    monkeypatch.setattr(limiter_module, "asyncio", SimpleNamespace(Lock=asyncio.Lock, sleep=sleep))
    return state


async def test_one_domain_serializes_concurrent_requests():
    limiter = RateLimiter(requests_per_second=50)
    starts = []

    async def request():
        await limiter.acquire("example.com")
        starts.append(time.monotonic())

    await asyncio.gather(*(request() for _ in range(4)))
    assert all(b - a >= 0.018 for a, b in zip(starts, starts[1:]))


async def test_different_domains_have_independent_limits(fake_clock):
    limiter = RateLimiter(2)
    await limiter.acquire("FIRST.example")
    await limiter.acquire("second.example")
    assert fake_clock.waits == []
    await limiter.acquire("first.example")
    assert fake_clock.waits == [0.5]


async def test_global_limit_applies_across_domains(fake_clock):
    limiter = RateLimiter(2, per_domain=False)
    await limiter.acquire("first.example")
    await limiter.acquire("second.example")
    await limiter.acquire()
    assert fake_clock.waits == [0.5, 0.5]


async def test_strictest_delay_plus_jitter_is_used(fake_clock, monkeypatch):
    monkeypatch.setattr(limiter_module.random, "uniform", lambda low, high: high)
    limiter = RateLimiter(10, min_delay=0.2, jitter=0.05)
    await limiter.acquire("example.com")
    await limiter.acquire("example.com", crawl_delay=0.4)
    await limiter.acquire("example.com")
    assert fake_clock.waits == pytest.approx([0.45, 0.25])
    stats = limiter.get_stats()
    assert stats["requests"] == 3
    assert stats["average_delay"] == pytest.approx(0.35)
    assert stats["requests_per_second"] == 3
    fake_clock.now += 2
    assert limiter.get_stats()["requests_per_second"] == 0


async def test_idle_time_does_not_accumulate_burst_permissions(fake_clock):
    limiter = RateLimiter(1)
    await limiter.acquire()
    fake_clock.now += 10
    await limiter.acquire()
    await limiter.acquire()
    assert fake_clock.waits == [1.0]


async def test_reset_stats_preserves_spacing(fake_clock):
    limiter = RateLimiter(2)
    await limiter.acquire()
    limiter.reset_stats()
    await limiter.acquire()
    assert fake_clock.waits == [0.5]
    assert limiter.get_stats()["requests"] == 1


async def test_cancelled_waiter_does_not_hold_lock():
    limiter = RateLimiter(50)
    await limiter.acquire("example.com")
    task = asyncio.create_task(limiter.acquire("example.com"))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(limiter.acquire("example.com"), timeout=1)
    assert limiter.get_stats()["requests"] == 2


@pytest.mark.parametrize("rate", [0, -1, True, "2", None, float("inf"), float("nan")])
def test_invalid_rate_is_rejected(rate):
    with pytest.raises(ValueError):
        RateLimiter(rate)


@pytest.mark.parametrize("options", [{"min_delay": -1}, {"jitter": float("inf")}, {"per_domain": 1}])
def test_invalid_options_are_rejected(options):
    with pytest.raises(ValueError):
        RateLimiter(**options)
