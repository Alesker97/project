"""Повторы асинхронных операций с учётом класса ошибки."""

import asyncio
import contextvars
import logging
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import aiohttp

from src.concurrency.rate_limiter import validate_delay
from src.crawler.errors import (
    CrawlerError,
    NetworkError,
    PermanentError,
    TransientError,
)


logger = logging.getLogger(__name__)
T = TypeVar("T")
retry_attempt: contextvars.ContextVar[int] = contextvars.ContextVar(
    "retry_attempt", default=0,
)


class RetryStrategy:
    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        retry_on: list[type[Exception]] | tuple[type[Exception], ...] | type[Exception] | None = None,
        *,
        max_backoff: float = 30.0,
        retries_by_type: dict[type[Exception], int] | None = None,
        backoff_by_type: dict[type[Exception], float] | None = None,
    ) -> None:
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries должен быть неотрицательным целым числом.")
        self.max_retries = max_retries
        self.backoff_factor = validate_delay(backoff_factor, "backoff_factor")
        self.max_backoff = validate_delay(max_backoff, "max_backoff")
        if retry_on is None:
            retry_on = (TransientError, NetworkError)
        elif isinstance(retry_on, type):
            retry_on = (retry_on,)
        if not isinstance(retry_on, (list, tuple)) or not all(
            isinstance(item, type) and issubclass(item, Exception)
            for item in retry_on
        ):
            raise ValueError("retry_on должен содержать классы исключений.")
        self.retry_on = tuple(retry_on)
        self.retries_by_type = dict(retries_by_type or {})
        self.backoff_by_type = dict(backoff_by_type or {})
        for error_type, limit in self.retries_by_type.items():
            if not isinstance(error_type, type) or not issubclass(error_type, Exception):
                raise ValueError("Ключи retries_by_type должны быть классами исключений.")
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
                raise ValueError("Лимит повторов должен быть неотрицательным целым числом.")
        for error_type, factor in self.backoff_by_type.items():
            if not isinstance(error_type, type) or not issubclass(error_type, Exception):
                raise ValueError("Ключи backoff_by_type должны быть классами исключений.")
            validate_delay(factor, "Множитель backoff")
        self.reset_stats()

    def reset_stats(self) -> None:
        self.error_counts: Counter[str] = Counter()
        self.successful_retries = 0
        self.retries = 0
        self.retry_wait_total = 0.0
        self.permanent_urls: set[str] = set()
        self.events: list[dict[str, object]] = []

    def get_stats(self) -> dict[str, object]:
        return {
            "errors_by_type": dict(self.error_counts),
            "successful_retries": self.successful_retries,
            "retries": self.retries,
            "average_retry_time": (
                self.retry_wait_total / self.retries if self.retries else 0.0
            ),
            "permanent_urls": sorted(self.permanent_urls),
        }

    async def execute_with_retry(
        self,
        coro: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        url = kwargs.get("url")
        if not isinstance(url, str):
            url = args[0] if args and isinstance(args[0], str) else ""
        attempt = 0
        while True:
            token = retry_attempt.set(attempt)
            try:
                result = await coro(*args, **kwargs)
            except asyncio.CancelledError:
                raise
            except Exception as original_error:
                error = self._classify(original_error, url)
                self.error_counts[type(error).__name__] += 1
                error_url = getattr(error, "url", "") or url
                if isinstance(error, PermanentError) and error_url:
                    self.permanent_urls.add(error_url)
                limit = self._retry_limit(error)
                should_retry = attempt < limit
                delay = self._delay(error, attempt) if should_retry else 0.0
                self.events.append({
                    "url": error_url,
                    "attempt": attempt + 1,
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "next_delay": delay if should_retry else None,
                    "result": "retry" if should_retry else "failed",
                })
                logger.warning(
                    "Ошибка %s для %s, попытка %s, следующая пауза %.2f сек, результат: %s",
                    type(error).__name__, error_url, attempt + 1, delay,
                    "повтор" if should_retry else "неудача",
                )
                if not should_retry:
                    if error is original_error:
                        raise
                    raise error from original_error
                self.retries += 1
                started = time.monotonic()
                await asyncio.sleep(delay)
                self.retry_wait_total += time.monotonic() - started
                attempt += 1
            else:
                if attempt:
                    self.successful_retries += 1
                self.events.append({
                    "url": url,
                    "attempt": attempt + 1,
                    "error_type": None,
                    "next_delay": None,
                    "result": "success",
                })
                logger.info("Успех для %s, попытка %s", url, attempt + 1)
                return result
            finally:
                retry_attempt.reset(token)

    def _retry_limit(self, error: Exception) -> int:
        if isinstance(error, PermanentError) or not isinstance(error, self.retry_on):
            return 0
        for error_type, limit in self.retries_by_type.items():
            if isinstance(error, error_type):
                return min(self.max_retries, limit)
        if isinstance(error, TransientError) and error.status == 500:
            return min(self.max_retries, 2)
        return self.max_retries

    @staticmethod
    def _classify(error: Exception, url: str) -> Exception:
        if isinstance(error, CrawlerError):
            return error
        if isinstance(error, asyncio.TimeoutError):
            return TransientError("Превышено время ожидания.", url=url)
        if isinstance(error, (aiohttp.ClientConnectionError, aiohttp.ClientPayloadError)):
            return NetworkError(f"{type(error).__name__}: {error}", url=url)
        return error

    def _delay(self, error: Exception, attempt: int) -> float:
        multiplier = 2.0 if isinstance(error, TransientError) and error.status == 429 else 1.0
        for error_type, factor in self.backoff_by_type.items():
            if isinstance(error, error_type):
                multiplier *= factor
                break
        return min(self.backoff_factor * (2 ** attempt) * multiplier, self.max_backoff)
