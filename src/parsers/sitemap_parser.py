"""Асинхронная загрузка обычных и индексных XML sitemap."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

import aiohttp


logger = logging.getLogger(__name__)


class SitemapParser:
    def __init__(
        self,
        *,
        fetcher: Callable[[str], Awaitable[str]] | None = None,
        max_sitemaps: int = 100,
        timeout: float = 30.0,
        user_agent: str = "AsyncCrawler/1.0",
    ) -> None:
        if isinstance(max_sitemaps, bool) or not isinstance(max_sitemaps, int) or max_sitemaps <= 0:
            raise ValueError("max_sitemaps должен быть положительным целым числом.")
        self._fetcher = fetcher
        self._max_sitemaps = max_sitemaps
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._user_agent = user_agent
        self._session: aiohttp.ClientSession | None = None

    async def fetch_sitemap(self, sitemap_url: str) -> list[str]:
        """Возвращает уникальные URL страниц в порядке появления."""
        self._validate_url(sitemap_url)
        visited: set[str] = set()
        page_urls: list[str] = []
        known_pages: set[str] = set()

        async def visit(url: str) -> None:
            if url in visited:
                return
            if len(visited) >= self._max_sitemaps:
                raise ValueError("Превышен лимит файлов sitemap.")
            visited.add(url)
            xml = await self._download(url)
            try:
                root = await asyncio.to_thread(ElementTree.fromstring, xml)
            except ElementTree.ParseError as error:
                raise ValueError(f"Некорректный sitemap {url}: {error}") from error
            kind = self._local_name(root.tag)
            if kind not in {"urlset", "sitemapindex"}:
                raise ValueError(f"Неизвестный формат sitemap: {url}")
            item_name = "url" if kind == "urlset" else "sitemap"
            for item in root:
                if self._local_name(item.tag) != item_name:
                    continue
                location = next(
                    (node.text.strip() for node in item
                     if self._local_name(node.tag) == "loc" and node.text and node.text.strip()),
                    None,
                )
                if location is None:
                    continue
                target = urljoin(url, location)
                self._validate_url(target)
                if kind == "sitemapindex":
                    await visit(target)
                elif target not in known_pages:
                    known_pages.add(target)
                    page_urls.append(target)

        await visit(sitemap_url)
        return page_urls

    async def _download(self, url: str) -> str:
        if self._fetcher is not None:
            return await self._fetcher(url)
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                headers={"User-Agent": self._user_agent},
            )
        async with self._session.get(url) as response:
            response.raise_for_status()
            return await response.text()

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Sitemap содержит некорректный HTTP- или HTTPS-адрес.")
