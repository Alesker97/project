"""Командный интерфейс полного обхода."""

import argparse
import asyncio
import json
from pathlib import Path

from src.crawler.advanced_crawler import AdvancedCrawler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Асинхронный веб-краулер")
    parser.add_argument("--config", help="Путь к JSON-конфигурации")
    parser.add_argument("--urls", nargs="+", help="Стартовые URL")
    parser.add_argument("--sitemaps", nargs="+", help="URL файлов sitemap.xml")
    parser.add_argument("--max-pages", type=int, help="Максимальное число страниц")
    parser.add_argument("--max-depth", type=int, help="Максимальная глубина ссылок")
    parser.add_argument("--output", help="Файл страниц: .jsonl, .json, .csv или .db")
    parser.add_argument("--respect-robots", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--rate-limit", type=float, help="Запросов в секунду")
    parser.add_argument("--stats-json", help="Файл сводной статистики JSON")
    parser.add_argument("--html-report", help="HTML-отчёт")
    return parser


def settings_from_args(args: argparse.Namespace) -> dict:
    if args.config:
        with Path(args.config).open("r", encoding="utf-8") as file:
            settings = json.load(file)
        if not isinstance(settings, dict):
            raise ValueError("Конфигурация должна быть объектом JSON.")
    else:
        settings = {}
    if args.urls is not None:
        settings["start_urls"] = args.urls
    if args.sitemaps is not None:
        settings["sitemaps"] = args.sitemaps
    if args.max_pages is not None:
        settings.setdefault("crawl", {})["max_pages"] = args.max_pages
    if args.max_depth is not None:
        settings.setdefault("crawler", {})["max_depth"] = args.max_depth
    if args.rate_limit is not None:
        settings.setdefault("crawler", {})["requests_per_second"] = args.rate_limit
    if args.respect_robots is not None:
        settings.setdefault("crawler", {})["respect_robots"] = args.respect_robots
    if args.output is not None:
        suffix = Path(args.output).suffix.lower()
        formats = {".jsonl": "jsonl", ".json": "json", ".csv": "csv", ".db": "sqlite", ".sqlite": "sqlite"}
        if suffix not in formats:
            raise ValueError("--output должен иметь расширение .jsonl, .json, .csv, .db или .sqlite.")
        settings["storage"] = {"format": formats[suffix], "path": args.output}
    if args.stats_json is not None:
        settings.setdefault("reports", {})["json"] = args.stats_json
    if args.html_report is not None:
        settings.setdefault("reports", {})["html"] = args.html_report
    return settings


async def run(settings: dict) -> dict[str, object]:
    crawler = AdvancedCrawler.from_settings(settings)
    try:
        await crawler.crawl()
        stats = crawler.get_stats()
        if "json" in crawler.report_paths:
            crawler.export_to_json(crawler.report_paths["json"])
        if "html" in crawler.report_paths:
            crawler.export_to_html_report(crawler.report_paths["html"])
        print(
            f"Обработано: {stats.total_pages}; успешно: {stats.successful}; "
            f"ошибок: {stats.failed}; скорость: {stats.average_speed:.2f} стр/с"
        )
        return stats.to_dict()
    finally:
        await crawler.close()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = settings_from_args(args)
        if not settings.get("start_urls") and not settings.get("sitemaps"):
            parser.error("укажите --urls, --sitemaps или задайте их в --config")
        asyncio.run(run(settings))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(2, f"Ошибка: {error}\n")
    return 0
