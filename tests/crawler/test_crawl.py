from collections.abc import AsyncIterator
from functools import partial

import pytest
from aiohttp import web

from src.crawler.async_crawler import AsyncCrawler


# Эти тесты проверяют загрузку и обход без правил вежливости.
create_crawler = partial(
    AsyncCrawler,
    requests_per_second=1000.0,
    respect_robots=False,
    max_retries=0,
)


@pytest.fixture
async def crawl_site(
) -> AsyncIterator[
    tuple[str, dict[str, int]]
]:
    counters: dict[str, int] = {}

    def register_request(path: str) -> None:
        counters[path] = counters.get(path, 0) + 1

    async def root_handler(
        request: web.Request,
    ) -> web.Response:
        register_request(request.path)

        return web.Response(
            text="""
            <html>
            <head><title>Главная</title></head>
            <body>
                <a href="/page-a">Страница A</a>
                <a href="/page-b">Страница B</a>
                <a href="/duplicate">Дубликат 1</a>
                <a href="/duplicate">Дубликат 2</a>
                <a href="/excluded">Исключённая</a>
                <a href="/error">Ошибка</a>
                <a href="https://external.example.com/page">
                    Внешняя
                </a>
            </body>
            </html>
            """,
            content_type="text/html",
        )

    async def page_a_handler(
        request: web.Request,
    ) -> web.Response:
        register_request(request.path)

        return web.Response(
            text="""
            <html>
            <head><title>Страница A</title></head>
            <body>
                <a href="/deep-a">Глубокая A</a>
                <a href="/duplicate">Дубликат</a>
            </body>
            </html>
            """,
            content_type="text/html",
        )

    async def page_b_handler(
        request: web.Request,
    ) -> web.Response:
        register_request(request.path)

        return web.Response(
            text="""
            <html>
            <head><title>Страница B</title></head>
            <body>
                <a href="/deep-b">Глубокая B</a>
                <a href="/duplicate">Дубликат</a>
            </body>
            </html>
            """,
            content_type="text/html",
        )

    async def simple_handler(
        request: web.Request,
    ) -> web.Response:
        register_request(request.path)

        return web.Response(
            text=(
                "<html><body>"
                f"<h1>{request.path}</h1>"
                "</body></html>"
            ),
            content_type="text/html",
        )

    async def error_handler(
        request: web.Request,
    ) -> web.Response:
        register_request(request.path)

        return web.Response(
            text="Ошибка сервера",
            status=500,
        )

    application = web.Application()
    application.router.add_get(
        "/",
        root_handler,
    )
    application.router.add_get(
        "/page-a",
        page_a_handler,
    )
    application.router.add_get(
        "/page-b",
        page_b_handler,
    )
    application.router.add_get(
        "/duplicate",
        simple_handler,
    )
    application.router.add_get(
        "/excluded",
        simple_handler,
    )
    application.router.add_get(
        "/deep-a",
        simple_handler,
    )
    application.router.add_get(
        "/deep-b",
        simple_handler,
    )
    application.router.add_get(
        "/error",
        error_handler,
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
        yield (
            f"http://127.0.0.1:{port}",
            counters,
        )
    finally:
        await runner.cleanup()


def get_paths(
    urls,
    base_url: str,
) -> set[str]:
    return {
        url.removeprefix(base_url)
        for url in urls
    }


@pytest.mark.parametrize(
    "max_depth",
    [
        -1,
        1.5,
        True,
    ],
)
def test_init_rejects_invalid_max_depth(
    max_depth,
) -> None:
    with pytest.raises(
        ValueError,
        match="Максимальная глубина",
    ):
        AsyncCrawler(max_depth=max_depth)


@pytest.mark.parametrize(
    "max_pages",
    [
        0,
        -1,
        1.5,
        True,
    ],
)
async def test_crawl_rejects_invalid_max_pages(
    max_pages,
) -> None:
    crawler = create_crawler()

    try:
        with pytest.raises(
            ValueError,
            match="Максимальное количество страниц",
        ):
            await crawler.crawl(
                ["https://example.com"],
                max_pages=max_pages,
            )
    finally:
        await crawler.close()


async def test_crawl_rejects_empty_start_urls(
) -> None:
    crawler = create_crawler()

    try:
        with pytest.raises(
            ValueError,
            match="хотя бы один стартовый URL",
        ):
            await crawler.crawl([])
    finally:
        await crawler.close()


async def test_crawl_rejects_invalid_start_url(
) -> None:
    crawler = create_crawler()

    try:
        with pytest.raises(
            ValueError,
            match="корректный HTTP- или HTTPS-адрес",
        ):
            await crawler.crawl(
                ["invalid-url"]
            )
    finally:
        await crawler.close()


@pytest.mark.parametrize(
    (
        "max_depth",
        "expected_processed_paths",
        "expected_failed_paths",
    ),
    [
        (
            0,
            {"/"},
            set(),
        ),
        (
            1,
            {
                "/",
                "/page-a",
                "/page-b",
                "/duplicate",
                "/excluded",
            },
            {
                "/error",
            },
        ),
        (
            2,
            {
                "/",
                "/page-a",
                "/page-b",
                "/duplicate",
                "/excluded",
                "/deep-a",
                "/deep-b",
            },
            {
                "/error",
            },
        ),
    ],
)
async def test_crawl_respects_max_depth(
    crawl_site,
    max_depth: int,
    expected_processed_paths: set[str],
    expected_failed_paths: set[str],
) -> None:
    base_url, _ = crawl_site
    crawler = create_crawler(
        max_concurrent=4,
        max_concurrent_per_domain=2,
        max_depth=max_depth,
    )

    try:
        results = await crawler.crawl(
            [f"{base_url}/"],
            max_pages=20,
            same_domain_only=True,
        )

        assert get_paths(
            results,
            base_url,
        ) == expected_processed_paths
        assert get_paths(
            crawler.failed_urls,
            base_url,
        ) == expected_failed_paths
        assert all(
            depth <= max_depth
            for depth in crawler._url_depths.values()
        )
    finally:
        await crawler.close()


async def test_crawl_filters_external_domains(
    crawl_site,
) -> None:
    base_url, _ = crawl_site
    crawler = create_crawler(max_depth=1)

    try:
        await crawler.crawl(
            [f"{base_url}/"],
            max_pages=20,
            same_domain_only=True,
        )

        assert (
            "https://external.example.com/page"
            not in crawler.visited_urls
        )
        assert (
            "https://external.example.com/page"
            not in crawler._url_depths
        )
    finally:
        await crawler.close()


async def test_crawl_applies_exclude_patterns(
    crawl_site,
) -> None:
    base_url, _ = crawl_site
    crawler = create_crawler(max_depth=1)

    try:
        results = await crawler.crawl(
            [f"{base_url}/"],
            max_pages=20,
            same_domain_only=True,
            exclude_patterns=[
                "/excluded",
                "/error",
            ],
        )

        paths = get_paths(results, base_url)

        assert "/excluded" not in paths
        assert "/error" not in get_paths(
            crawler.failed_urls,
            base_url,
        )
        assert crawler.failed_urls == {}
    finally:
        await crawler.close()


async def test_crawl_applies_include_patterns(
    crawl_site,
) -> None:
    base_url, _ = crawl_site
    crawler = create_crawler(max_depth=2)

    try:
        results = await crawler.crawl(
            [f"{base_url}/"],
            max_pages=20,
            same_domain_only=True,
            include_patterns=[
                "/page-",
            ],
        )

        assert get_paths(results, base_url) == {
            "/",
            "/page-a",
            "/page-b",
        }
    finally:
        await crawler.close()


async def test_crawl_processes_duplicate_once(
    crawl_site,
) -> None:
    base_url, counters = crawl_site
    crawler = create_crawler(max_depth=2)

    try:
        await crawler.crawl(
            [f"{base_url}/"],
            max_pages=20,
            same_domain_only=True,
        )

        duplicate_url = (
            f"{base_url}/duplicate"
        )

        assert counters["/duplicate"] == 1
        assert duplicate_url in crawler.visited_urls
        assert (
            list(crawler.visited_urls).count(
                duplicate_url
            )
            == 1
        )
    finally:
        await crawler.close()


async def test_crawl_records_failed_urls(
    crawl_site,
) -> None:
    base_url, _ = crawl_site
    crawler = create_crawler(max_depth=1)

    try:
        await crawler.crawl(
            [f"{base_url}/"],
            max_pages=20,
            same_domain_only=True,
        )

        error_url = f"{base_url}/error"

        assert crawler.failed_urls == {
            error_url: "HTTP 500",
        }
        assert (
            error_url
            not in crawler.processed_urls
        )
        assert crawler._queue.get_stats() == {
            "queued": 0,
            "active": 0,
            "processed": 5,
            "failed": 1,
            "total": 6,
        }
    finally:
        await crawler.close()


async def test_crawl_respects_max_pages(
    crawl_site,
) -> None:
    base_url, _ = crawl_site
    crawler = create_crawler(max_depth=2)

    try:
        results = await crawler.crawl(
            [f"{base_url}/"],
            max_pages=3,
            same_domain_only=True,
        )

        assert len(crawler.visited_urls) == 3
        assert len(results) == 3
        assert get_paths(results, base_url) == {
            "/",
            "/page-a",
            "/page-b",
        }
    finally:
        await crawler.close()


async def test_crawl_displays_progress_and_stats(
    crawl_site,
    capsys: pytest.CaptureFixture,
) -> None:
    base_url, _ = crawl_site
    crawler = create_crawler(max_depth=1)

    try:
        await crawler.crawl(
            [f"{base_url}/"],
            max_pages=20,
            same_domain_only=True,
        )

        output = capsys.readouterr().out
        stats = crawler.get_crawl_stats()

        assert "Обработано:" in output
        assert "В очереди:" in output
        assert "Ошибок:" in output
        assert "Скорость:" in output
        assert stats["processed"] == 6
        assert stats["successful"] == 5
        assert stats["queued"] == 0
        assert stats["active"] == 0
        assert stats["failed"] == 1
        assert stats["speed"] > 0
    finally:
        await crawler.close()


async def test_crawl_resets_previous_state(
    crawl_site,
) -> None:
    base_url, _ = crawl_site
    crawler = create_crawler(max_depth=1)

    try:
        await crawler.crawl(
            [f"{base_url}/"],
            max_pages=3,
            same_domain_only=True,
        )

        second_results = await crawler.crawl(
            [f"{base_url}/duplicate"],
            max_pages=1,
            same_domain_only=True,
        )

        duplicate_url = (
            f"{base_url}/duplicate"
        )

        assert second_results.keys() == {
            duplicate_url,
        }
        assert crawler.visited_urls == {
            duplicate_url,
        }
        assert crawler.failed_urls == {}
        assert crawler._url_depths == {
            duplicate_url: 0,
        }
    finally:
        await crawler.close()
