import asyncio
import logging
import time

from src.crawler.async_crawler import AsyncCrawler


URLS = [
    "https://example.com",
    "https://httpbin.org/delay/1?request=1",
    "https://httpbin.org/delay/1?request=2",
    "https://httpbin.org/delay/1?request=3",
    "https://httpbin.org/delay/1?request=4",
    "https://httpbin.org/status/404",
]


async def fetch_sequentially(
    crawler: AsyncCrawler,
    urls: list[str],
) -> dict[str, str]:
    results = {}

    for url in urls:
        results[url] = await crawler.fetch_url(url)

    return results


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


async def main() -> None:
    sequential_crawler = AsyncCrawler(max_concurrent=5)
    parallel_crawler = AsyncCrawler(max_concurrent=5)

    try:
        sequential_started_at = time.perf_counter()
        sequential_results = await fetch_sequentially(
            sequential_crawler,
            URLS,
        )
        sequential_duration = (
            time.perf_counter() - sequential_started_at
        )

        parallel_started_at = time.perf_counter()
        parallel_results = await parallel_crawler.fetch_urls(
            URLS
        )
        parallel_duration = (
            time.perf_counter() - parallel_started_at
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


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | %(levelname)s | %(message)s"
        ),
    )
    asyncio.run(main())
