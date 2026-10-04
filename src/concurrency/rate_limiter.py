import asyncio
import math
import random
import time
from collections import deque


def validate_delay(value: float, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(
            f"{name} должен быть конечным неотрицательным числом."
        )
    return float(value)


class RateLimiter:
    """Разделяет начала запросов интервалом без накопления разрешений."""

    def __init__(
        self,
        requests_per_second: float = 1.0,
        per_domain: bool = True,
        *,
        min_delay: float = 0.0,
        jitter: float = 0.0,
    ) -> None:
        rate = validate_delay(requests_per_second, "Скорость запросов")
        if rate == 0 or not math.isfinite(1.0 / rate):
            raise ValueError("Скорость запросов должна быть положительной.")
        if not isinstance(per_domain, bool):
            raise ValueError("per_domain должен быть логическим значением.")

        self._interval = 1.0 / rate
        self._per_domain = per_domain
        self._min_delay = validate_delay(min_delay, "min_delay")
        self._jitter = validate_delay(jitter, "jitter")
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_request: dict[str, float] = {}
        self._recent_requests: deque[float] = deque()
        self._requests = 0
        self._delay_total = 0.0
        self._delay_count = 0

    async def acquire(
        self,
        domain: str | None = None,
        *,
        crawl_delay: float = 0.0,
    ) -> None:
        delay = validate_delay(crawl_delay, "Crawl-delay")
        if domain is not None and (
            not isinstance(domain, str) or not domain.strip()
        ):
            raise ValueError("Домен должен быть непустой строкой.")
        # Без домена все вызовы используют один общий лимит.
        key = (domain or "").strip().lower() if self._per_domain else ""
        lock = self._locks.setdefault(key, asyncio.Lock())

        async with lock:
            previous = self._last_request.get(key)
            if previous is not None:
                interval = max(self._interval, self._min_delay, delay)
                interval += random.uniform(0.0, self._jitter)
                remaining = previous + interval - time.monotonic()
                while remaining > 0:
                    await asyncio.sleep(remaining)
                    remaining = previous + interval - time.monotonic()

            started_at = time.monotonic()
            if previous is not None:
                self._delay_total += started_at - previous
                self._delay_count += 1
            self._last_request[key] = started_at
            self._requests += 1
            self._recent_requests.append(started_at)
            self._trim_recent(started_at)

    def get_stats(self) -> dict[str, int | float]:
        self._trim_recent(time.monotonic())
        return {
            "requests": self._requests,
            "requests_per_second": float(len(self._recent_requests)),
            "average_delay": (
                self._delay_total / self._delay_count
                if self._delay_count else 0.0
            ),
        }

    def reset_stats(self) -> None:
        # Сохраняем последние разрешения, чтобы новый обход не обходил лимит.
        self._recent_requests.clear()
        self._requests = 0
        self._delay_total = 0.0
        self._delay_count = 0

    def _trim_recent(self, now: float) -> None:
        while self._recent_requests and self._recent_requests[0] <= now - 1.0:
            self._recent_requests.popleft()
