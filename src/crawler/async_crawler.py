import asyncio
import logging
import aiohttp

from src.parsers.html_parser import HTMLParser


logger = logging.getLogger(__name__)


class AsyncCrawler:
    def __init__(self, max_concurrent: int = 10) -> None:
        if (
            isinstance(max_concurrent, bool)
            or not isinstance(max_concurrent, int)
            or max_concurrent <= 0
        ):
            raise ValueError(
                "Количество параллельных запросов должно быть "
                "положительным целым числом."
            )

        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._timeout = aiohttp.ClientTimeout(
            connect=10,
            sock_read=30,
        )
        self._session: aiohttp.ClientSession | None = None
        self._parser = HTMLParser()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=self._max_concurrent,
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=self._timeout,
            )

        return self._session

    async def fetch_url(self, url: str) -> str:
        logger.info("Начало загрузки URL: %s", url)

        try:
            session = await self._get_session()

            async with self._semaphore:
                async with session.get(url) as response:
                    response.raise_for_status()
                    content = await response.text()

            logger.info("Успешная загрузка URL: %s", url)
            return content
        except aiohttp.ClientResponseError as error:
            logger.error(
                "HTTP-ошибка при загрузке URL %s: статус %s",
                url,
                error.status,
            )
        except asyncio.TimeoutError as error:
            logger.error(
                "Таймаут при загрузке URL %s: %s",
                url,
                type(error).__name__,
            )
        except aiohttp.ClientError as error:
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

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
