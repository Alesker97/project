"""Запуск краулера: python crawler.py --urls https://example.com."""

from src.cli import main
from src.crawler.advanced_crawler import AdvancedCrawler

__all__ = ["AdvancedCrawler", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
