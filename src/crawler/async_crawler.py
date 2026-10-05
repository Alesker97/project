import asyncio
import logging
import time
from datetime import datetime, timezone
from urllib.parse import urldefrag, urljoin, urlparse

import aiohttp

from src.concurrency.semaphore_manager import (
    SemaphoreManager,
)
from src.concurrency.rate_limiter import RateLimiter, validate_delay
from src.crawler.errors import (
    CrawlerError, NetworkError, ParseError, PermanentError, TransientError,
)
from src.crawler.retry_strategy import RetryStrategy, retry_attempt
from src.parsers.html_parser import HTMLParser
from src.parsers.robots_parser import RobotsParser, RobotsResponse
from src.queues.crawler_queue import CrawlerQueue
from src.storage.base import DataStorage


logger = logging.getLogger(__name__)


class _RobotsBlockedError(Exception):
    pass


class AsyncCrawler:
    def __init__(
        self,
        max_concurrent: int = 10,
        max_concurrent_per_domain: int = 2,
        max_depth: int = 2,
        *,
        requests_per_second: float = 1.0,
        per_domain: bool = True,
        respect_robots: bool = True,
        min_delay: float = 0.0,
        jitter: float = 0.0,
        user_agent: str = "AsyncCrawler/1.0",
        max_retries: int = 2,
        backoff_factor: float = 0.5,
        max_backoff: float = 30.0,
        retry_strategy: RetryStrategy | None = None,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
        total_timeout: float | None = None,
        storage: DataStorage | None = None,
        storage_retries: int = 2,
        storage_backoff: float = 0.05,
    ) -> None:
        if (
            isinstance(max_concurrent, bool)
            or not isinstance(max_concurrent, int)
            or max_concurrent <= 0
        ):
            raise ValueError(
                "Количество параллельных запросов должно быть "
                "положительным целым числом."
            )

        if (
            isinstance(max_depth, bool)
            or not isinstance(max_depth, int)
            or max_depth < 0
        ):
            raise ValueError(
                "Максимальная глубина должна быть "
                "неотрицательным целым числом."
            )

        if not isinstance(respect_robots, bool):
            raise ValueError("respect_robots должен быть логическим значением.")
        if (
            not isinstance(user_agent, str)
            or not user_agent.strip()
            or "\r" in user_agent
            or "\n" in user_agent
        ):
            raise ValueError("User-Agent должен быть непустой строкой без переносов.")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries должен быть неотрицательным целым числом.")

        self._rate_limiter = RateLimiter(
            requests_per_second,
            per_domain,
            min_delay=min_delay,
            jitter=jitter,
        )
        self._respect_robots = respect_robots
        self._user_agent = user_agent.strip()
        if retry_strategy is not None and not isinstance(retry_strategy, RetryStrategy):
            raise ValueError("retry_strategy должен быть экземпляром RetryStrategy.")
        self.retry_strategy = retry_strategy or RetryStrategy(
            max_retries=max_retries,
            backoff_factor=backoff_factor,
            max_backoff=max_backoff,
        )
        self._max_retries = max_retries
        self._backoff_factor = validate_delay(backoff_factor, "backoff_factor")
        self._max_backoff = validate_delay(max_backoff, "max_backoff")
        self._connect_timeout = validate_delay(connect_timeout, "connect_timeout")
        self._read_timeout = validate_delay(read_timeout, "read_timeout")
        self._total_timeout = (
            None if total_timeout is None else validate_delay(total_timeout, "total_timeout")
        )
        if self._connect_timeout == 0 or self._read_timeout == 0 or self._total_timeout == 0:
            raise ValueError("Таймауты должны быть положительными.")
        if storage is not None and not isinstance(storage, DataStorage):
            raise ValueError("storage должен быть экземпляром DataStorage.")
        if isinstance(storage_retries, bool) or not isinstance(storage_retries, int) or storage_retries < 0:
            raise ValueError("storage_retries должен быть неотрицательным целым числом.")
        self.storage = storage
        self._storage_retries = storage_retries
        self._storage_backoff = validate_delay(storage_backoff, "storage_backoff")
        self._stored_count = 0
        self._storage_retry_count = 0
        self.storage_failed_urls: dict[str, str] = {}
        self._response_details: dict[str, tuple[int, str]] = {}
        self._page_response_details: dict[str, tuple[int, str]] = {}
        self.blocked_urls: set[str] = set()
        self._robots_parser = RobotsParser(
            user_agent=self._user_agent,
            fetcher=self._fetch_robots_request,
        )
        self._max_concurrent = max_concurrent
        self._max_concurrent_per_domain = (
            max_concurrent_per_domain
        )
        self._max_depth = max_depth
        self._semaphore_manager = SemaphoreManager(
            global_limit=max_concurrent,
            per_domain_limit=(
                max_concurrent_per_domain
            ),
        )
        self._timeout = aiohttp.ClientTimeout(
            connect=self._connect_timeout,
            sock_read=self._read_timeout,
            total=self._total_timeout,
        )
        self._session: aiohttp.ClientSession | None = None
        self._parser = HTMLParser()
        self._queue = CrawlerQueue()
        self._url_depths: dict[str, int] = {}
        self._allowed_domains: set[str] = set()
        self._same_domain_only = False
        self._include_patterns: list[str] = []
        self._exclude_patterns: list[str] = []
        self._crawl_started_at: float | None = None
        self.visited_urls: set[str] = set()
        self.failed_urls: dict[str, str] = {}
        self.processed_urls: dict[
            str,
            dict[str, object],
        ] = {}

    async def _get_session(
        self,
    ) -> aiohttp.ClientSession:
        if (
            self._session is None
            or self._session.closed
        ):
            connector = aiohttp.TCPConnector(
                limit=self._max_concurrent,
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=self._timeout,
                headers={"User-Agent": self._user_agent},
            )

        return self._session

    async def fetch_url(self, url: str, *, raise_on_error: bool = False) -> str:
        self.failed_urls.pop(url, None)

        logger.info("Начало загрузки URL: %s", url)

        try:
            current_url = url
            for _ in range(11):
                if raise_on_error:
                    status, content, location = await self._request_once(
                        current_url, check_robots=self._respect_robots,
                    )
                else:
                    status, content, location = await self._request_with_retries(
                        current_url, check_robots=self._respect_robots,
                    )
                if status in {301, 302, 303, 307, 308} and location:
                    current_url = urljoin(current_url, location)
                    continue
                if status >= 400:
                    self._page_response_details[url] = self._response_details.get(
                        current_url, (status, ""),
                    )
                    error_type = TransientError if status == 429 or status >= 500 else PermanentError
                    raise error_type(f"HTTP {status}", url=url, status=status, content=content)
                break
            else:
                raise ValueError("Слишком много перенаправлений страницы.")

            logger.info("Успешная загрузка URL: %s", url)
            self._page_response_details[url] = self._response_details.get(
                current_url, (status, ""),
            )
            return content
        except _RobotsBlockedError as error:
            self.blocked_urls.add(url)
            self.failed_urls[url] = f"Заблокировано robots.txt: {error}"
            logger.warning("URL %s заблокирован robots.txt: %s", url, error)
            if raise_on_error:
                raise PermanentError(str(error), url=url) from error
        except CrawlerError as error:
            if isinstance(error, TransientError) and error.status is None:
                self.failed_urls[url] = "Превышено время ожидания."
                logger.error("Таймаут при загрузке URL %s: %s", url, type(error).__name__)
            elif isinstance(error, PermanentError) and error.status is None:
                self.failed_urls[url] = f"ValueError: {error}"
                logger.error("Сетевая ошибка при загрузке URL %s: %s", url, type(error).__name__)
            elif isinstance(error, NetworkError):
                self.failed_urls[url] = str(error)
                logger.error("Сетевая ошибка при загрузке URL %s: %s", url, type(error).__name__)
            else:
                self.failed_urls[url] = str(error)
                logger.error("HTTP-ошибка при загрузке URL %s: %s (%s)", url, error, type(error).__name__)
            if raise_on_error:
                raise
        except aiohttp.ClientResponseError as error:
            self.failed_urls[url] = (
                f"HTTP {error.status}"
            )
            logger.error(
                "HTTP-ошибка при загрузке URL %s: статус %s",
                url,
                error.status,
            )
        except asyncio.TimeoutError as error:
            self.failed_urls[url] = (
                "Превышено время ожидания."
            )
            logger.error(
                "Таймаут при загрузке URL %s: %s",
                url,
                type(error).__name__,
            )
            if raise_on_error:
                raise TransientError("Превышено время ожидания.", url=url) from error
        except (
            aiohttp.ClientError,
            ValueError,
        ) as error:
            self.failed_urls[url] = (
                f"{type(error).__name__}: {error}"
            )
            logger.error(
                "Сетевая ошибка при загрузке URL %s: %s",
                url,
                type(error).__name__,
            )
            if raise_on_error:
                if isinstance(error, ValueError):
                    raise PermanentError(str(error), url=url) from error
                raise NetworkError(str(error), url=url) from error

        return ""

    async def _request_with_retries(
        self,
        url: str,
        *,
        check_robots: bool = False,
        allow_not_found: bool = False,
    ) -> RobotsResponse:
        try:
            return await self.retry_strategy.execute_with_retry(
                self._request_once, url, check_robots=check_robots,
                allow_not_found=allow_not_found,
            )
        except CrawlerError as error:
            if error.status is not None:
                return error.status, error.content, error.location
            raise

    async def _fetch_robots_request(self, url: str) -> RobotsResponse:
        return await self._request_with_retries(url, allow_not_found=True)

    async def _request_once(
        self, url: str, *, check_robots: bool = False,
        allow_not_found: bool = False,
    ) -> RobotsResponse:
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise PermanentError("Ожидается корректный HTTP- или HTTPS-адрес.", url=url)
        crawl_delay = 0.0
        if check_robots:
            await self._robots_parser.fetch_robots(url)
            if not self._robots_parser.can_fetch(url, self._user_agent):
                raise _RobotsBlockedError(url)
            crawl_delay = self._robots_parser.get_crawl_delay(self._user_agent, url=url)
        session = await self._get_session()
        scale = 1.5 ** retry_attempt.get()
        timeout = aiohttp.ClientTimeout(
            total=None if self._timeout.total is None else self._timeout.total * scale,
            connect=None if self._timeout.connect is None else self._timeout.connect * scale,
            sock_read=None if self._timeout.sock_read is None else self._timeout.sock_read * scale,
        )
        try:
            async with self._semaphore_manager.limit(url):
                await self._rate_limiter.acquire(parsed_url.hostname, crawl_delay=crawl_delay)
                async with session.get(url, allow_redirects=False, timeout=timeout) as response:
                    result = (
                        response.status,
                        await response.text(),
                        response.headers.get("Location"),
                    )
                    self._response_details[url] = (
                        response.status,
                        response.headers.get("Content-Type", "").split(";", 1)[0].strip(),
                    )
        except asyncio.TimeoutError as error:
            raise TransientError("Превышено время ожидания.", url=url) from error
        except (aiohttp.ClientConnectionError, aiohttp.ClientPayloadError) as error:
            raise NetworkError(f"{type(error).__name__}: {error}", url=url) from error
        status, content, location = result
        if status >= 400 and not (allow_not_found and status == 404):
            error_type = TransientError if status == 429 or status >= 500 else PermanentError
            raise error_type(
                f"HTTP {status}", url=url, status=status,
                content=content, location=location,
            )
        return result

    async def fetch_urls(
        self,
        urls: list[str],
    ) -> dict[str, str]:
        contents = await asyncio.gather(
            *(self.fetch_url(url) for url in urls)
        )

        return dict(
            zip(
                urls,
                contents,
                strict=True,
            )
        )

    async def fetch_and_parse(
        self,
        url: str,
    ) -> dict[str, object]:
        html = await self.fetch_url(url)

        logger.info(
            "Начало парсинга URL: %s",
            url,
        )
        try:
            result = await self._parser.parse_html(html, url)
        except Exception as error:
            parse_error = ParseError(f"{type(error).__name__}: {error}", url=url)
            self.failed_urls[url] = str(parse_error)
            self.retry_strategy.error_counts["ParseError"] += 1
            self.retry_strategy.events.append({
                "url": url,
                "attempt": 1,
                "error_type": "ParseError",
                "error": str(parse_error),
                "next_delay": None,
                "result": "failed",
            })
            logger.error("Ошибка парсинга URL %s: %s", url, parse_error)
            raise parse_error from error
        logger.info(
            "Парсинг URL завершён: %s",
            url,
        )

        if url not in self.failed_urls:
            await self._save_page(url, result)

        return result

    async def crawl(
        self,
        start_urls: list[str],
        max_pages: int = 100,
        same_domain_only: bool = False,
        exclude_patterns: list[str] | None = None,
        include_patterns: list[str] | None = None,
    ) -> dict[str, dict[str, object]]:
        if (
            isinstance(max_pages, bool)
            or not isinstance(max_pages, int)
            or max_pages <= 0
        ):
            raise ValueError(
                "Максимальное количество страниц должно быть "
                "положительным целым числом."
            )

        if not isinstance(same_domain_only, bool):
            raise ValueError(
                "Параметр same_domain_only должен быть "
                "логическим значением."
            )

        normalized_start_urls = (
            self._normalize_start_urls(start_urls)
        )
        normalized_exclude_patterns = (
            self._normalize_patterns(
                exclude_patterns,
                "exclude_patterns",
            )
        )
        normalized_include_patterns = (
            self._normalize_patterns(
                include_patterns,
                "include_patterns",
            )
        )

        self._reset_crawl_state()
        self._same_domain_only = same_domain_only
        self._exclude_patterns = (
            normalized_exclude_patterns
        )
        self._include_patterns = (
            normalized_include_patterns
        )
        self._allowed_domains = {
            domain
            for url in normalized_start_urls
            if (
                domain
                := urlparse(url).hostname
            )
            is not None
        }

        for url in normalized_start_urls:
            self._url_depths[url] = 0
            self._queue.add_url(
                url,
                priority=0,
            )

        while len(self.visited_urls) < max_pages:
            remaining_pages = (
                max_pages - len(self.visited_urls)
            )
            batch_limit = min(
                self._max_concurrent,
                remaining_pages,
            )
            batch = []

            while len(batch) < batch_limit:
                url = await self._queue.get_next()

                if url is None:
                    break

                if url in self.visited_urls:
                    self._queue.mark_processed(url)
                    continue

                self.visited_urls.add(url)
                batch.append(url)

            if not batch:
                break

            await asyncio.gather(
                *(
                    self._process_crawl_url(url)
                    for url in batch
                )
            )

        await self._flush_storage()
        return dict(self.processed_urls)

    def get_crawl_stats(
        self,
    ) -> dict[str, int | float]:
        successful = len(self.processed_urls)
        failed = len(self.failed_urls)
        completed = successful + failed
        queue_stats = self._queue.get_stats()

        if self._crawl_started_at is None:
            speed = 0.0
        else:
            elapsed = max(
                time.perf_counter()
                - self._crawl_started_at,
                0.000001,
            )
            speed = completed / elapsed

        return {
            "processed": completed,
            "successful": successful,
            "queued": queue_stats["queued"],
            "active": queue_stats["active"],
            "failed": failed,
            "speed": speed,
            **self.get_request_stats(),
        }

    def get_request_stats(self) -> dict[str, int | float]:
        return {
            **self._rate_limiter.get_stats(),
            "blocked": len(self.blocked_urls),
            "retries": self.retry_strategy.retries,
        }

    def get_error_stats(self) -> dict[str, object]:
        return self.retry_strategy.get_stats()

    def get_error_report(self) -> dict[str, object]:
        return {
            "statistics": self.get_error_stats(),
            "failed_urls": dict(self.failed_urls),
            "attempts": list(self.retry_strategy.events),
        }

    def get_storage_stats(self) -> dict[str, object]:
        return {
            "saved": self._stored_count,
            "failed": len(self.storage_failed_urls),
            "retries": self._storage_retry_count,
            "failed_urls": dict(self.storage_failed_urls),
        }

    async def close(self) -> None:
        await self._robots_parser.close()
        if (
            self._session is not None
            and not self._session.closed
        ):
            await self._session.close()
        if self.storage is not None:
            try:
                await self.storage.close()
            except Exception as error:
                logger.error("Ошибка закрытия хранилища: %s", error)

    async def _process_crawl_url(
        self,
        url: str,
    ) -> None:
        try:
            result = await self.fetch_and_parse(url)

            if url in self.failed_urls:
                self._queue.mark_failed(
                    url,
                    self.failed_urls[url],
                )
                return

            self.processed_urls[url] = result
            self._queue.mark_processed(url)
            self._add_discovered_links(
                url,
                result,
            )
        except Exception as error:
            failure_reason = (
                f"{type(error).__name__}: {error}"
            )
            self.failed_urls[url] = failure_reason
            self._queue.mark_failed(
                url,
                failure_reason,
            )
            logger.exception(
                "Непредвиденная ошибка обработки URL %s",
                url,
            )
        finally:
            self._display_progress()

    async def _save_page(self, url: str, result: dict[str, object]) -> None:
        if self.storage is None:
            return
        status_code, content_type = self._page_response_details.get(url, (200, ""))
        record = {
            "url": url,
            "title": result["title"],
            "text": result["text"],
            "links": result["links"],
            "metadata": result["metadata"],
            "crawled_at": datetime.now(timezone.utc),
            "status_code": status_code,
            "content_type": content_type,
        }
        for attempt in range(self._storage_retries + 1):
            try:
                await self.storage.save(record)
            except Exception as error:
                if attempt == self._storage_retries:
                    self.storage_failed_urls[url] = f"{type(error).__name__}: {error}"
                    logger.error("Не удалось сохранить URL %s после %s попыток: %s", url, attempt + 1, error)
                    return
                self._storage_retry_count += 1
                delay = self._storage_backoff * (2 ** attempt)
                logger.warning("Ошибка сохранения URL %s, попытка %s, повтор через %.2f сек: %s", url, attempt + 1, delay, error)
                await asyncio.sleep(delay)
            else:
                self._stored_count += 1
                self.storage_failed_urls.pop(url, None)
                return

    async def _flush_storage(self) -> None:
        if self.storage is None:
            return
        for attempt in range(self._storage_retries + 1):
            try:
                await self.storage.flush()
            except Exception as error:
                if attempt == self._storage_retries:
                    for url in self.storage.pending_urls:
                        if url not in self.storage_failed_urls:
                            self._stored_count -= 1
                        self.storage_failed_urls[url] = f"{type(error).__name__}: {error}"
                    logger.error("Не удалось сбросить буфер хранилища: %s", error)
                    return
                self._storage_retry_count += 1
                await asyncio.sleep(self._storage_backoff * (2 ** attempt))
            else:
                return

    def _add_discovered_links(
        self,
        source_url: str,
        result: dict[str, object],
    ) -> None:
        current_depth = self._url_depths[source_url]
        next_depth = current_depth + 1

        if next_depth > self._max_depth:
            return

        links = result.get("links", [])

        if not isinstance(links, list):
            return

        for link in links:
            if not isinstance(link, str):
                continue

            if (
                link in self.visited_urls
                or link in self._url_depths
            ):
                continue

            if not self._is_url_allowed(link):
                continue

            self._url_depths[link] = next_depth
            self._queue.add_url(
                link,
                priority=-next_depth,
            )

    def _is_url_allowed(
        self,
        url: str,
    ) -> bool:
        parsed_url = urlparse(url)
        domain = parsed_url.hostname

        if (
            parsed_url.scheme not in {"http", "https"}
            or domain is None
        ):
            return False

        if (
            self._same_domain_only
            and domain not in self._allowed_domains
        ):
            return False

        if (
            self._include_patterns
            and not any(
                pattern in url
                for pattern in self._include_patterns
            )
        ):
            return False

        if any(
            pattern in url
            for pattern in self._exclude_patterns
        ):
            return False

        return True

    def _reset_crawl_state(self) -> None:
        self.visited_urls.clear()
        self.failed_urls.clear()
        self.processed_urls.clear()
        self.blocked_urls.clear()
        self.storage_failed_urls.clear()
        self._stored_count = 0
        self._storage_retry_count = 0
        self._response_details.clear()
        self._page_response_details.clear()
        self.retry_strategy.reset_stats()
        self._rate_limiter.reset_stats()
        self._url_depths = {}
        self._allowed_domains = set()
        self._queue = CrawlerQueue()
        self._crawl_started_at = time.perf_counter()
        self._semaphore_manager = SemaphoreManager(
            global_limit=self._max_concurrent,
            per_domain_limit=(
                self._max_concurrent_per_domain
            ),
        )

    def _display_progress(self) -> None:
        stats = self.get_crawl_stats()

        print(
            f"Обработано: {stats['processed']} | "
            f"В очереди: {stats['queued']} | "
            f"Ошибок: {stats['failed']} | "
            f"Скорость: {stats['speed']:.2f} стр/сек | "
            f"Запросы: {stats['requests_per_second']:.2f} req/sec | "
            f"Средняя задержка: {stats['average_delay']:.3f} сек | "
            f"Блокировок robots.txt: {stats['blocked']}",
            flush=True,
        )

    @staticmethod
    def _normalize_start_urls(
        start_urls: list[str],
    ) -> list[str]:
        if (
            not isinstance(start_urls, list)
            or not start_urls
        ):
            raise ValueError(
                "Необходимо передать хотя бы один "
                "стартовый URL."
            )

        normalized_urls = []
        known_urls = set()

        for url in start_urls:
            if (
                not isinstance(url, str)
                or not url.strip()
            ):
                raise ValueError(
                    "Стартовый URL должен быть "
                    "непустой строкой."
                )

            normalized_url, _ = urldefrag(
                url.strip()
            )
            parsed_url = urlparse(normalized_url)

            if (
                parsed_url.scheme
                not in {"http", "https"}
                or parsed_url.hostname is None
            ):
                raise ValueError(
                    "Стартовый URL должен содержать "
                    "корректный HTTP- или HTTPS-адрес."
                )

            if normalized_url in known_urls:
                continue

            known_urls.add(normalized_url)
            normalized_urls.append(normalized_url)

        return normalized_urls

    @staticmethod
    def _normalize_patterns(
        patterns: list[str] | None,
        parameter_name: str,
    ) -> list[str]:
        if patterns is None:
            return []

        if not isinstance(patterns, list):
            raise ValueError(
                f"{parameter_name} должен быть списком."
            )

        normalized_patterns = []

        for pattern in patterns:
            if (
                not isinstance(pattern, str)
                or not pattern
            ):
                raise ValueError(
                    f"Все элементы {parameter_name} "
                    "должны быть непустыми строками."
                )

            normalized_patterns.append(pattern)

        return normalized_patterns
