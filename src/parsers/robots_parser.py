import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import aiohttp

from src.concurrency.rate_limiter import validate_delay


logger = logging.getLogger(__name__)
RobotsResponse = tuple[int, str, str | None]


@dataclass
class _RobotsRules:
    parser: RobotFileParser
    delays: list[tuple[list[str], float | None]]
    status: int | None


class RobotsParser:
    """Асинхронная загрузка и кэш robots.txt по origin (схема, хост, порт)."""

    def __init__(
        self,
        *,
        user_agent: str = "AsyncCrawler/1.0",
        fetcher: Callable[[str], Awaitable[RobotsResponse]] | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._fetcher = fetcher
        self._session: aiohttp.ClientSession | None = None
        self._cache: dict[str, _RobotsRules] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_origin: str | None = None

    @staticmethod
    def _origin(url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Ожидается корректный HTTP- или HTTPS-адрес.")
        port = parsed.port
        host = parsed.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        if port is not None and port != (443 if parsed.scheme == "https" else 80):
            host = f"{host}:{port}"
        return f"{parsed.scheme}://{host}"

    async def fetch_robots(self, base_url: str) -> dict[str, object]:
        origin = self._origin(base_url)
        async with self._locks.setdefault(origin, asyncio.Lock()):
            if origin not in self._cache:
                self._cache[origin] = await self._load(origin)

        self._last_origin = origin
        rules = self._cache[origin]
        return {
            "url": f"{origin}/robots.txt",
            "status": rules.status,
            "crawl_delay": self.get_crawl_delay(self._user_agent, url=base_url),
            "disallow_all": rules.parser.disallow_all,
        }

    def can_fetch(self, url: str, user_agent: str = "*") -> bool:
        rules = self._cache.get(self._origin(url))
        return rules is not None and rules.parser.can_fetch(user_agent, url)

    def get_crawl_delay(
        self,
        user_agent: str = "*",
        *,
        url: str | None = None,
    ) -> float:
        # Явный URL обязателен при конкурентной работе с разными сайтами.
        origin = self._origin(url) if url is not None else self._last_origin
        rules = self._cache.get(origin) if origin is not None else None
        if rules is None:
            return 0.0
        product = user_agent.split("/")[0].lower()
        fallback = None
        for agents, delay in rules.delays:
            if any(agent != "*" and agent in product for agent in agents):
                return delay or 0.0
            if "*" in agents and fallback is None:
                fallback = delay or 0.0
        return fallback or 0.0

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def _download(self, url: str) -> RobotsResponse:
        if self._fetcher is not None:
            return await self._fetcher(url)
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": self._user_agent},
                timeout=aiohttp.ClientTimeout(total=30),
            )
        async with self._session.get(url, allow_redirects=False) as response:
            return response.status, await response.text(), response.headers.get("Location")

    async def _load(self, origin: str) -> _RobotsRules:
        robots_url = f"{origin}/robots.txt"
        parser = RobotFileParser(robots_url)
        status = None
        text = ""
        try:
            current_url = robots_url
            for _ in range(6):
                status, text, location = await self._download(current_url)
                if status in {301, 302, 303, 307, 308} and location:
                    current_url = urljoin(current_url, location)
                    self._origin(current_url)
                    continue
                break
            else:
                raise ValueError("Слишком много перенаправлений robots.txt.")

            if status in {401, 403, 429} or status >= 500 or 300 <= status < 400:
                parser.disallow_all = True
            elif status >= 400:
                # Отсутствующий robots.txt не запрещает обход.
                parser.allow_all = True
            else:
                parser.parse(text.splitlines())
            logger.info("Загружен robots.txt: %s, статус %s", robots_url, status)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
            parser.disallow_all = True
            logger.warning("Не удалось загрузить %s: %s", robots_url, error)

        delays = self._parse_delays(text) if not parser.disallow_all else []
        return _RobotsRules(parser, delays, status)

    @staticmethod
    def _parse_delays(text: str) -> list[tuple[list[str], float | None]]:
        """Crawl-delay допускает дробные секунды в дополнение к целым."""
        groups: list[tuple[list[str], float | None]] = []
        agents: list[str] = []
        delay = None
        has_directives = False
        for raw_line in [*text.splitlines(), ""]:
            if raw_line.lstrip().startswith("#"):
                continue
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                if agents:
                    groups.append((agents, delay))
                agents, delay, has_directives = [], None, False
                continue
            key, separator, value = line.partition(":")
            if not separator:
                continue
            key, value = key.strip().lower(), value.strip()
            if key == "user-agent":
                if has_directives:
                    groups.append((agents, delay))
                    agents, delay, has_directives = [], None, False
                agents.append(value.lower())
            elif agents:
                has_directives = True
                if key == "crawl-delay":
                    try:
                        delay = validate_delay(float(value), "Crawl-delay")
                    except ValueError:
                        pass
        return groups
