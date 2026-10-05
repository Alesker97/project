"""Сравнение асинхронного и последовательного обхода локального сайта."""

import asyncio
import json
import time
import tracemalloc
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import ProxyHandler, build_opener

from aiohttp import web
from bs4 import BeautifulSoup

from src.crawler.advanced_crawler import AdvancedCrawler


def _crawl_sync(base_url: str, expected_pages: int) -> int:
    opener = build_opener(ProxyHandler({}))
    with opener.open(base_url, timeout=10) as response:
        root_html = response.read().decode("utf-8")
    soup = BeautifulSoup(root_html, "lxml")
    urls = [urljoin(base_url, link["href"]) for link in soup.find_all("a", href=True)]
    for url in urls:
        with opener.open(url, timeout=10) as response:
            BeautifulSoup(response.read(), "lxml")
    return 1 + len(urls)


async def _measure_async(base_url: str, size: int) -> tuple[float, int, int]:
    crawler = AdvancedCrawler(
        [base_url], max_pages=size, max_depth=1,
        max_concurrent=20, max_concurrent_per_domain=20,
        requests_per_second=1_000_000, respect_robots=False,
        max_retries=0, show_progress=False,
    )
    tracemalloc.start()
    started = time.perf_counter()
    try:
        pages = await crawler.crawl()
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        return elapsed, peak, len(pages)
    finally:
        tracemalloc.stop()
        await crawler.close()


async def run_benchmark(
    sizes: tuple[int, ...] = (100, 500, 1000),
    *,
    output: str | Path | None = "output/benchmark.json",
) -> list[dict[str, float | int]]:
    results = []
    for size in sizes:
        if size <= 0:
            raise ValueError("Размер набора страниц должен быть положительным.")

        async def handle(request: web.Request) -> web.Response:
            if request.path == "/":
                html = "".join(f'<a href="/page/{index}">Ссылка</a>' for index in range(size - 1))
            else:
                html = "<title>Локальная страница</title><p>Данные</p>"
            return web.Response(text=html, content_type="text/html")

        app = web.Application()
        app.router.add_get("/{path:.*}", handle)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        try:
            await web.TCPSite(runner, "127.0.0.1", 0).start()
            base_url = f"http://127.0.0.1:{runner.addresses[0][1]}"
            tracemalloc.start()
            started = time.perf_counter()
            sync_count = await asyncio.to_thread(_crawl_sync, base_url, size)
            sync_seconds = time.perf_counter() - started
            _, sync_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            async_seconds, async_peak, async_count = await _measure_async(base_url, size)
            if sync_count != size or async_count != size:
                raise RuntimeError("Краулеры обработали разное число страниц.")
            row = {
                "pages": size,
                "sync_seconds": round(sync_seconds, 4),
                "async_seconds": round(async_seconds, 4),
                "speedup": round(sync_seconds / async_seconds, 3),
                "sync_peak_bytes": sync_peak,
                "async_peak_bytes": async_peak,
            }
            results.append(row)
            print(
                f"{size} страниц: синхронно {sync_seconds:.2f} с, "
                f"асинхронно {async_seconds:.2f} с, "
                f"ускорение {row['speedup']:.2f}x, "
                f"память {async_peak / 1024 / 1024:.1f} МиБ",
            )
        finally:
            await runner.cleanup()
    if output is not None:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    asyncio.run(run_benchmark())
