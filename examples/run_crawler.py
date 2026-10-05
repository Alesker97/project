"""Пример запуска полного краулера с JSON-конфигурацией."""

import asyncio

from crawler import AdvancedCrawler


async def main() -> None:
    crawler = AdvancedCrawler.from_config("config.example.json")
    try:
        await crawler.crawl()
        stats = crawler.get_stats()
        print(f"Обработано: {stats.total_pages}")
        print(f"Успешно: {stats.successful}")
        print(f"Ошибок: {stats.failed}")
        crawler.export_to_json("output/stats.json")
        crawler.export_to_html_report("output/report.html")
    finally:
        await crawler.close()


if __name__ == "__main__":
    asyncio.run(main())
