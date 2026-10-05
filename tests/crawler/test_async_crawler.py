import asyncio
from functools import partial
import logging
import time
from collections.abc import AsyncIterator
import aiohttp
import pytest
from aiohttp import web

from src.concurrency.semaphore_manager import (
    SemaphoreManager,
)
from src.crawler.async_crawler import AsyncCrawler


# Эти тесты проверяют загрузку и обход без правил вежливости.
create_crawler = partial(
    AsyncCrawler,
    requests_per_second=1000.0,
    respect_robots=False,
    max_retries=0,
)


async def success_handler(
    request: web.Request,
) -> web.Response:
    return web.Response(text="Успешный ответ")


async def not_found_handler(
    request: web.Request,
) -> web.Response:
    return web.Response(
        text="Страница не найдена",
        status=404,
    )


async def slow_handler(
    request: web.Request,
) -> web.Response:
    await asyncio.sleep(0.2)
    return web.Response(text="Медленный ответ")


async def html_handler(
    request: web.Request,
) -> web.Response:
    return web.Response(
        text="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Страница краулера</title>
            <meta
                name="description"
                content="Описание страницы краулера"
            >
            <meta
                name="keywords"
                content="crawler, asyncio"
            >
        </head>
        <body>
            <main>
                <h1>Асинхронный краулер</h1>
                <p>Текст тестовой страницы</p>
                <a href="/next#section">
                    Следующая страница
                </a>
                <img
                    src="/images/logo.png"
                    alt="Логотип"
                >
                <ul>
                    <li>Первый пункт</li>
                    <li>Второй пункт</li>
                </ul>
            </main>
        </body>
        </html>
        """,
        content_type="text/html",
    )


@pytest.fixture
async def local_server_url() -> AsyncIterator[str]:
    application = web.Application()
    application.router.add_get(
        "/success",
        success_handler,
    )
    application.router.add_get(
        "/missing",
        not_found_handler,
    )
    application.router.add_get(
        "/slow",
        slow_handler,
    )
    application.router.add_get(
        "/html",
        html_handler,
    )

    runner = web.AppRunner(application)
    await runner.setup()

    site = web.TCPSite(
        runner,
        host="127.0.0.1",
        port=0,
    )
    await site.start()

    server = site._server

    assert server is not None
    assert server.sockets

    port = server.sockets[0].getsockname()[1]

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        await runner.cleanup()


def test_init_uses_default_max_concurrent() -> None:
    crawler = AsyncCrawler()

    assert crawler._max_concurrent == 10
    assert crawler._max_concurrent_per_domain == 2
    assert crawler._max_depth == 2
    assert isinstance(
        crawler._semaphore_manager,
        SemaphoreManager,
    )
    assert (
        crawler._semaphore_manager._global_limit
        == 10
    )
    assert (
        crawler._semaphore_manager._per_domain_limit
        == 2
    )
    assert crawler._session is None
    assert crawler.visited_urls == set()
    assert crawler.failed_urls == {}
    assert crawler.processed_urls == {}


@pytest.mark.parametrize(
    "max_concurrent",
    [
        0,
        -1,
        1.5,
        "5",
        True,
        None,
    ],
)
def test_init_rejects_invalid_max_concurrent(
    max_concurrent,
) -> None:
    with pytest.raises(
        ValueError,
        match="Количество параллельных запросов",
    ):
        AsyncCrawler(max_concurrent=max_concurrent)


@pytest.mark.parametrize(
    "max_concurrent_per_domain",
    [
        0,
        -1,
        1.5,
        True,
    ],
)
def test_init_rejects_invalid_domain_limit(
    max_concurrent_per_domain,
) -> None:
    with pytest.raises(
        ValueError,
        match="Доменный лимит",
    ):
        AsyncCrawler(
            max_concurrent_per_domain=(
                max_concurrent_per_domain
            )
        )


async def test_get_session_creates_configured_session() -> None:
    crawler = AsyncCrawler(max_concurrent=3)

    try:
        session = await crawler._get_session()

        assert isinstance(session, aiohttp.ClientSession)
        assert session.connector is not None
        assert session.connector.limit == 3
        assert session.timeout.connect == 10
        assert session.timeout.sock_read == 30
        assert session.closed is False
    finally:
        await crawler.close()


async def test_get_session_reuses_existing_session() -> None:
    crawler = AsyncCrawler()

    try:
        first_session = await crawler._get_session()
        second_session = await crawler._get_session()

        assert second_session is first_session
    finally:
        await crawler.close()


async def test_close_closes_session() -> None:
    crawler = AsyncCrawler()
    session = await crawler._get_session()

    await crawler.close()

    assert session.closed is True


async def test_close_can_be_called_multiple_times() -> None:
    crawler = AsyncCrawler()
    session = await crawler._get_session()

    await crawler.close()
    await crawler.close()

    assert session.closed is True


async def test_get_session_recreates_closed_session() -> None:
    crawler = AsyncCrawler()
    first_session = await crawler._get_session()

    await crawler.close()

    try:
        second_session = await crawler._get_session()

        assert second_session is not first_session
        assert second_session.closed is False
    finally:
        await crawler.close()


async def test_fetch_url_returns_response_content(
    local_server_url: str,
    caplog,
) -> None:
    crawler = create_crawler()
    url = f"{local_server_url}/success"
    caplog.set_level(
        logging.INFO,
        logger="src.crawler.async_crawler",
    )

    try:
        result = await crawler.fetch_url(url)

        assert result == "Успешный ответ"
        assert url not in crawler.failed_urls
        assert "Начало загрузки URL" in caplog.text
        assert "Успешная загрузка URL" in caplog.text
    finally:
        await crawler.close()


async def test_fetch_url_handles_http_error(
    local_server_url: str,
    caplog,
) -> None:
    crawler = create_crawler()
    url = f"{local_server_url}/missing"
    caplog.set_level(
        logging.ERROR,
        logger="src.crawler.async_crawler",
    )

    try:
        result = await crawler.fetch_url(url)

        assert result == ""
        assert crawler.failed_urls[url] == "HTTP 404"
        assert "HTTP-ошибка" in caplog.text
        assert "404" in caplog.text
    finally:
        await crawler.close()


async def test_fetch_url_handles_timeout(
    local_server_url: str,
    caplog,
) -> None:
    crawler = create_crawler()
    crawler._timeout = aiohttp.ClientTimeout(
        connect=1,
        sock_read=0.05,
    )
    url = f"{local_server_url}/slow"
    caplog.set_level(
        logging.ERROR,
        logger="src.crawler.async_crawler",
    )

    try:
        result = await crawler.fetch_url(url)

        assert result == ""
        assert crawler.failed_urls[url] == (
            "Превышено время ожидания."
        )
        assert "Таймаут при загрузке URL" in caplog.text
    finally:
        await crawler.close()


async def test_fetch_url_handles_invalid_url(
    caplog,
) -> None:
    crawler = create_crawler()
    url = "invalid-url"
    caplog.set_level(
        logging.ERROR,
        logger="src.crawler.async_crawler",
    )

    try:
        result = await crawler.fetch_url(url)

        assert result == ""
        assert crawler.failed_urls[url].startswith(
            "ValueError:"
        )
        assert "Сетевая ошибка" in caplog.text
    finally:
        await crawler.close()


async def test_fetch_urls_returns_results_for_every_url(
    local_server_url: str,
) -> None:
    crawler = create_crawler(max_concurrent=3)
    urls = [
        f"{local_server_url}/success?request=1",
        f"{local_server_url}/success?request=2",
        f"{local_server_url}/success?request=3",
    ]

    try:
        results = await crawler.fetch_urls(urls)

        assert results == {
            urls[0]: "Успешный ответ",
            urls[1]: "Успешный ответ",
            urls[2]: "Успешный ответ",
        }
    finally:
        await crawler.close()


async def test_fetch_urls_keeps_failed_request_in_results(
    local_server_url: str,
) -> None:
    crawler = create_crawler(max_concurrent=2)
    success_url = f"{local_server_url}/success"
    missing_url = f"{local_server_url}/missing"
    urls = [
        success_url,
        missing_url,
    ]

    try:
        results = await crawler.fetch_urls(urls)

        assert results == {
            success_url: "Успешный ответ",
            missing_url: "",
        }
    finally:
        await crawler.close()


async def test_fetch_urls_accepts_empty_list() -> None:
    crawler = create_crawler()

    try:
        results = await crawler.fetch_urls([])

        assert results == {}
        assert crawler._session is None
    finally:
        await crawler.close()


async def test_parallel_loading_is_faster_than_sequential(
    local_server_url: str,
) -> None:
    urls = [
        f"{local_server_url}/slow?request=1",
        f"{local_server_url}/slow?request=2",
        f"{local_server_url}/slow?request=3",
    ]
    sequential_crawler = create_crawler(max_concurrent=1)
    parallel_crawler = create_crawler(max_concurrent=3)

    try:
        sequential_started_at = time.perf_counter()
        sequential_results = await sequential_crawler.fetch_urls(
            urls
        )
        sequential_duration = (
            time.perf_counter() - sequential_started_at
        )

        parallel_started_at = time.perf_counter()
        parallel_results = await parallel_crawler.fetch_urls(
            urls
        )
        parallel_duration = (
            time.perf_counter() - parallel_started_at
        )

        assert all(sequential_results.values())
        assert all(parallel_results.values())
        assert parallel_duration < sequential_duration
    finally:
        await sequential_crawler.close()
        await parallel_crawler.close()


async def test_fetch_and_parse_returns_structured_data(
    local_server_url: str,
) -> None:
    crawler = create_crawler()

    try:
        result = await crawler.fetch_and_parse(
            f"{local_server_url}/html"
        )

        assert result["url"] == (
            f"{local_server_url}/html"
        )
        assert result["title"] == (
            "Страница краулера"
        )
        assert (
            "Асинхронный краулер"
            in result["text"]
        )
        assert (
            "Текст тестовой страницы"
            in result["text"]
        )
        assert result["metadata"] == {
            "title": "Страница краулера",
            "description": (
                "Описание страницы краулера"
            ),
            "keywords": "crawler, asyncio",
        }
        assert result["headings"] == [
            {
                "level": "h1",
                "text": "Асинхронный краулер",
            }
        ]
        assert result["lists"] == [
            {
                "type": "ul",
                "items": [
                    "Первый пункт",
                    "Второй пункт",
                ],
            }
        ]
    finally:
        await crawler.close()


async def test_fetch_and_parse_resolves_relative_urls(
    local_server_url: str,
) -> None:
    crawler = create_crawler()
    page_url = f"{local_server_url}/html"

    try:
        result = await crawler.fetch_and_parse(
            page_url
        )

        assert result["links"] == [
            f"{local_server_url}/next"
        ]
        assert result["images"] == [
            {
                "src": (
                    f"{local_server_url}"
                    "/images/logo.png"
                ),
                "alt": "Логотип",
            }
        ]
    finally:
        await crawler.close()


async def test_fetch_and_parse_handles_http_error(
    local_server_url: str,
) -> None:
    crawler = create_crawler()
    page_url = f"{local_server_url}/missing"

    try:
        result = await crawler.fetch_and_parse(
            page_url
        )

        assert result == {
            "url": page_url,
            "title": "",
            "text": "",
            "links": [],
            "metadata": {
                "title": "",
                "description": "",
                "keywords": "",
            },
            "images": [],
            "headings": [],
            "tables": [],
            "lists": [],
        }
    finally:
        await crawler.close()


async def test_fetch_urls_respects_domain_limit(
    local_server_url: str,
) -> None:
    crawler = create_crawler(
        max_concurrent=3,
        max_concurrent_per_domain=1,
    )
    urls = [
        f"{local_server_url}/slow?request=domain-1",
        f"{local_server_url}/slow?request=domain-2",
        f"{local_server_url}/slow?request=domain-3",
    ]

    try:
        results = await crawler.fetch_urls(urls)
        stats = (
            crawler
            ._semaphore_manager
            .get_stats()
        )

        assert all(results.values())
        assert stats["active"] == 0
        assert stats["active_by_domain"] == {}
        assert stats["peak_active"] == 1
        assert stats["peak_by_domain"] == {
            "127.0.0.1": 1,
        }
    finally:
        await crawler.close()


async def test_successful_fetch_clears_previous_error(
    local_server_url: str,
) -> None:
    crawler = create_crawler()
    url = f"{local_server_url}/success"
    crawler.failed_urls[url] = "Старая ошибка"

    try:
        result = await crawler.fetch_url(url)

        assert result == "Успешный ответ"
        assert url not in crawler.failed_urls
    finally:
        await crawler.close()
