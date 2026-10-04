import asyncio
import logging
import time
from urllib.parse import urldefrag, urlparse

import aiohttp

from src.concurrency.semaphore_manager import (
    SemaphoreManager,
)
from src.parsers.html_parser import HTMLParser
from src.queues.crawler_queue import CrawlerQueue


logger = logging.getLogger(__name__)


class AsyncCrawler:
    def __init__(
        self,
        max_concurrent: int = 10,
        max_concurrent_per_domain: int = 2,
        max_depth: int = 2,
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
            connect=10,
            sock_read=30,
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
            )

        return self._session

    async def fetch_url(self, url: str) -> str:
        self.failed_urls.pop(url, None)

        logger.info("Начало загрузки URL: %s", url)

        try:
            session = await self._get_session()

            async with self._semaphore_manager.limit(
                url
            ):
                async with session.get(url) as response:
                    response.raise_for_status()
                    content = await response.text()

            logger.info("Успешная загрузка URL: %s", url)
            return content
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

        return ""

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
        result = await self._parser.parse_html(
            html,
            url,
        )
        logger.info(
            "Парсинг URL завершён: %s",
            url,
        )

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
        }

    async def close(self) -> None:
        if (
            self._session is not None
            and not self._session.closed
        ):
            await self._session.close()

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
            f"Скорость: {stats['speed']:.2f} стр/сек",
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
