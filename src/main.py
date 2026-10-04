import asyncio
import json
import logging
import time
from pathlib import Path
from typing import cast

import aiofiles

from src.crawler.async_crawler import AsyncCrawler


URLS = [
    "https://example.com",
    "https://httpbin.org/delay/1?request=1",
    "https://httpbin.org/delay/1?request=2",
    "https://httpbin.org/delay/1?request=3",
    "https://httpbin.org/delay/1?request=4",
    "https://httpbin.org/status/404",
]

PARSE_URLS = [
    "https://example.com",
    "https://httpbin.org/html",
    "https://www.python.org",
]

CRAWL_START_URLS = [
    "https://quotes.toscrape.com/",
]

CRAWL_OUTPUT_PATH = Path(
    "output/crawl_results.json"
)


async def fetch_sequentially(
    crawler: AsyncCrawler,
    urls: list[str],
) -> dict[str, str]:
    results = {}

    for url in urls:
        results[url] = await crawler.fetch_url(url)

    return results


async def fetch_and_parse_pages(
    crawler: AsyncCrawler,
    urls: list[str],
) -> list[dict[str, object]]:
    return await asyncio.gather(
        *(
            crawler.fetch_and_parse(url)
            for url in urls
        )
    )


async def save_crawl_results(
    results: dict[str, dict[str, object]],
    file_path: Path,
) -> None:
    await asyncio.to_thread(
        file_path.parent.mkdir,
        parents=True,
        exist_ok=True,
    )
    content = json.dumps(
        results,
        ensure_ascii=False,
        indent=2,
    )

    async with aiofiles.open(
        file_path,
        "w",
        encoding="utf-8",
    ) as file:
        await file.write(content)


def display_results(
    results: dict[str, str],
) -> None:
    for url, content in results.items():
        status = "успешно" if content else "ошибка"
        print(f"{url} | Статус: {status}")


def display_performance(
    sequential_duration: float,
    parallel_duration: float,
) -> None:
    print(
        "\nВремя последовательной загрузки:",
        f"{sequential_duration:.2f} сек.",
    )
    print(
        "Время параллельной загрузки:",
        f"{parallel_duration:.2f} сек.",
    )

    if parallel_duration < sequential_duration:
        acceleration = (
            sequential_duration / parallel_duration
        )
        print(
            "Параллельная загрузка быстрее в",
            f"{acceleration:.2f} раза.",
        )
    else:
        print(
            "В этом запуске параллельная загрузка "
            "не показала ускорения."
        )


def display_parsed_pages(
    pages: list[dict[str, object]],
) -> None:
    print("\nРезультаты парсинга страниц:")

    for page in pages:
        url = cast(str, page["url"])
        title = cast(str, page["title"])
        text = cast(str, page["text"])
        links = cast(list[str], page["links"])
        images = cast(
            list[dict[str, str]],
            page["images"],
        )
        headings = cast(
            list[dict[str, str]],
            page["headings"],
        )
        tables = cast(
            list[list[list[str]]],
            page["tables"],
        )
        lists = cast(
            list[dict[str, object]],
            page["lists"],
        )

        status = (
            "успешно"
            if text or title
            else "данные не получены"
        )

        print(f"\nURL: {url}")
        print(f"Статус: {status}")
        print(
            "Заголовок:",
            title or "не найден",
        )
        print(f"Длина текста: {len(text)}")
        print(f"Количество ссылок: {len(links)}")
        print(
            "Количество изображений:",
            len(images),
        )
        print(
            "Количество заголовков:",
            len(headings),
        )
        print(
            "Количество таблиц:",
            len(tables),
        )
        print(
            "Количество списков:",
            len(lists),
        )

        if headings:
            print("Заголовки h1–h3:")

            for heading in headings:
                print(
                    f"- {heading['level']}: "
                    f"{heading['text']}"
                )

        if links:
            print("Первые найденные ссылки:")

            for link in links[:5]:
                print(f"- {link}")


async def main() -> None:
    sequential_crawler = AsyncCrawler(
        max_concurrent=5
    )
    parallel_crawler = AsyncCrawler(
        max_concurrent=5
    )

    try:
        sequential_started_at = time.perf_counter()
        sequential_results = await fetch_sequentially(
            sequential_crawler,
            URLS,
        )
        sequential_duration = (
            time.perf_counter()
            - sequential_started_at
        )

        parallel_started_at = time.perf_counter()
        parallel_results = (
            await parallel_crawler.fetch_urls(URLS)
        )
        parallel_duration = (
            time.perf_counter()
            - parallel_started_at
        )

        parsed_pages = await fetch_and_parse_pages(
            parallel_crawler,
            PARSE_URLS,
        )
    finally:
        await sequential_crawler.close()
        await parallel_crawler.close()

    print("\nРезультаты последовательной загрузки:")
    display_results(sequential_results)

    print("\nРезультаты параллельной загрузки:")
    display_results(parallel_results)

    display_performance(
        sequential_duration,
        parallel_duration,
    )
    display_parsed_pages(parsed_pages)

    crawl_crawler = AsyncCrawler(
        max_concurrent=5,
        max_concurrent_per_domain=2,
        max_depth=2,
    )

    try:
        print("\nОбход сайта:")

        crawl_results = await crawl_crawler.crawl(
            start_urls=CRAWL_START_URLS,
            max_pages=10,
            same_domain_only=True,
            exclude_patterns=[
                "/login",
            ],
        )
        await save_crawl_results(
            crawl_results,
            CRAWL_OUTPUT_PATH,
        )

        crawl_stats = (
            crawl_crawler.get_crawl_stats()
        )

        print("\nИтог обхода:")
        print(
            "Успешно обработано:",
            crawl_stats["successful"],
        )
        print(
            "Ошибок:",
            crawl_stats["failed"],
        )
        print(
            "Скорость:",
            f"{crawl_stats['speed']:.2f} стр/сек",
        )
        print(
            "Результат сохранён:",
            CRAWL_OUTPUT_PATH,
        )
    finally:
        await crawl_crawler.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | %(levelname)s | %(message)s"
        ),
    )
    asyncio.run(main())
