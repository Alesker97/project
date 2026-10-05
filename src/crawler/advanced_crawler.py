"""Интеграция обхода, sitemap, конфигурации, хранения и статистики."""

import json
import inspect
import logging
import time
from pathlib import Path
from typing import Any

from src.crawler.async_crawler import AsyncCrawler
from src.crawler.logging_config import configure_logging
from src.crawler.stats import CrawlerStats
from src.parsers.sitemap_parser import SitemapParser
from src.storage import CSVStorage, DataStorage, JSONStorage, SQLiteStorage


logger = logging.getLogger(__name__)


def storage_from_config(settings: dict[str, Any]) -> DataStorage:
    if not isinstance(settings, dict):
        raise ValueError("storage должен быть объектом JSON.")
    kind = settings.get("format", "jsonl")
    path = settings.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError("storage.path должен быть непустой строкой.")
    options = {
        "jsonl": {"format", "path", "buffer_size"},
        "json": {"format", "path", "buffer_size", "indent"},
        "csv": {"format", "path", "buffer_size", "encoding"},
        "sqlite": {"format", "path", "batch_size"},
    }
    if not isinstance(kind, str) or kind not in options:
        raise ValueError("storage.format должен быть jsonl, json, csv или sqlite.")
    unknown = set(settings) - options[kind]
    if unknown:
        raise ValueError(f"Неизвестные параметры storage: {', '.join(sorted(unknown))}")
    if kind == "jsonl":
        return JSONStorage(path, buffer_size=settings.get("buffer_size", 1))
    if kind == "json":
        return JSONStorage(path, json_lines=False, indent=settings.get("indent", 2), buffer_size=settings.get("buffer_size", 1))
    if kind == "csv":
        return CSVStorage(path, encoding=settings.get("encoding", "utf-8"), buffer_size=settings.get("buffer_size", 1))
    if kind == "sqlite":
        return SQLiteStorage(path, batch_size=settings.get("batch_size", 1))
    raise AssertionError("Недостижимый формат storage.")


class AdvancedCrawler(AsyncCrawler):
    def __init__(
        self,
        start_urls: list[str] | None = None,
        *,
        sitemap_urls: list[str] | None = None,
        max_pages: int = 100,
        same_domain_only: bool = False,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        storage: DataStorage | None = None,
        show_progress: bool = True,
        report_paths: dict[str, str] | None = None,
        **crawler_options: Any,
    ) -> None:
        super().__init__(storage=storage, **crawler_options)
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages <= 0:
            raise ValueError("max_pages должен быть положительным целым числом.")
        if start_urls is not None and (not isinstance(start_urls, list) or not all(isinstance(url, str) for url in start_urls)):
            raise ValueError("start_urls должен быть списком URL.")
        if sitemap_urls is not None and (not isinstance(sitemap_urls, list) or not all(isinstance(url, str) for url in sitemap_urls)):
            raise ValueError("sitemap_urls должен быть списком URL.")
        self.start_urls = list(start_urls or [])
        self.sitemap_urls = list(sitemap_urls or [])
        self.max_pages = max_pages
        self._target_pages = max_pages
        self.same_domain_only = same_domain_only
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns
        self.show_progress = show_progress
        if not isinstance(show_progress, bool):
            raise ValueError("show_progress должен быть логическим значением.")
        self.report_paths = dict(report_paths or {})
        self.sitemap_parser = SitemapParser(
            fetcher=self._fetch_sitemap_text,
            user_agent=self._user_agent,
        )
        self.sitemap_errors: dict[str, str] = {}
        self._run_started_at: float | None = None
        self._run_finished_at: float | None = None
        self._last_progress_at = 0.0

    @classmethod
    def from_config(cls, filename: str | Path) -> "AdvancedCrawler":
        path = Path(filename)
        with path.open("r", encoding="utf-8") as file:
            settings = json.load(file)
        return cls.from_settings(settings)

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> "AdvancedCrawler":
        if not isinstance(settings, dict):
            raise ValueError("Конфигурация должна быть объектом JSON.")
        allowed = {"start_urls", "sitemaps", "crawler", "crawl", "storage", "logging", "reports"}
        unknown = set(settings) - allowed
        if unknown:
            raise ValueError(f"Неизвестные параметры конфигурации: {', '.join(sorted(unknown))}")
        for name in ("crawler", "crawl", "reports"):
            if name in settings and not isinstance(settings[name], dict):
                raise ValueError(f"{name} должен быть объектом JSON.")
        crawler_settings = dict(settings.get("crawler", {}))
        crawl_settings = dict(settings.get("crawl", {}))
        crawler_options = set(inspect.signature(AsyncCrawler.__init__).parameters) - {"self", "storage"}
        crawl_options = {"max_pages", "same_domain_only", "include_patterns", "exclude_patterns", "show_progress"}
        unknown_crawler = set(crawler_settings) - crawler_options
        unknown_crawl = set(crawl_settings) - crawl_options
        if unknown_crawler or unknown_crawl:
            unknown = sorted(unknown_crawler | unknown_crawl)
            raise ValueError(f"Неизвестные параметры краулера: {', '.join(unknown)}")
        log_settings = settings.get("logging")
        if log_settings is not None:
            if not isinstance(log_settings, dict) or "path" not in log_settings:
                raise ValueError("logging должен содержать путь path.")
            if set(log_settings) - {"path", "level", "max_bytes", "backup_count"}:
                raise ValueError("Неизвестные параметры logging.")
            configure_logging(**log_settings)
        reports = settings.get("reports", {})
        if set(reports) - {"json", "html"} or any(
            not isinstance(path, str) or not path for path in reports.values()
        ):
            raise ValueError("reports должен содержать пути json и/или html.")
        storage = storage_from_config(settings["storage"]) if "storage" in settings else None
        return cls(
            start_urls=settings.get("start_urls", []),
            sitemap_urls=settings.get("sitemaps", []),
            storage=storage,
            report_paths=reports,
            **crawl_settings,
            **crawler_settings,
        )

    async def _fetch_sitemap_text(self, url: str) -> str:
        status, content, _ = await self._request_with_retries(
            url, check_robots=self._respect_robots,
        )
        if status >= 400:
            raise ValueError(f"Sitemap {url} вернул HTTP {status}.")
        return content

    async def crawl(
        self,
        start_urls: list[str] | None = None,
        max_pages: int | None = None,
        same_domain_only: bool | None = None,
        exclude_patterns: list[str] | None = None,
        include_patterns: list[str] | None = None,
    ) -> dict[str, dict[str, object]]:
        seeds = list(self.start_urls if start_urls is None else start_urls)
        self.sitemap_errors.clear()
        self._run_started_at = time.perf_counter()
        self._run_finished_at = None
        for sitemap_url in self.sitemap_urls:
            try:
                seeds.extend(await self.sitemap_parser.fetch_sitemap(sitemap_url))
            except Exception as error:
                self.sitemap_errors[sitemap_url] = f"{type(error).__name__}: {error}"
                logger.error("Не удалось обработать sitemap %s: %s", sitemap_url, error)
        if not seeds:
            raise ValueError("Нужен хотя бы один стартовый URL или доступный sitemap.")
        self._target_pages = self.max_pages if max_pages is None else max_pages
        completed = False
        try:
            result = await super().crawl(
                seeds,
                max_pages=self._target_pages,
                same_domain_only=self.same_domain_only if same_domain_only is None else same_domain_only,
                exclude_patterns=self.exclude_patterns if exclude_patterns is None else exclude_patterns,
                include_patterns=self.include_patterns if include_patterns is None else include_patterns,
            )
            completed = True
            return result
        finally:
            if completed:
                self._run_finished_at = time.perf_counter()
            if self.show_progress:
                self._display_progress(force=True)

    def get_stats(self) -> CrawlerStats:
        if self._run_started_at is None:
            duration = 0.0
        else:
            duration = max((self._run_finished_at or time.perf_counter()) - self._run_started_at, 0.0)
        return CrawlerStats.from_crawler(
            self, run_time=duration, target_pages=self._target_pages,
            finished=self._run_finished_at is not None,
        )

    def export_to_json(self, filename: str | Path) -> None:
        self.get_stats().export_to_json(filename)

    def export_to_html_report(self, filename: str | Path) -> None:
        self.get_stats().export_to_html_report(filename)

    def _display_progress(self, *, force: bool = False) -> None:
        if not self.show_progress:
            return
        now = time.perf_counter()
        if not force and now - self._last_progress_at < 0.5:
            return
        self._last_progress_at = now
        stats = self.get_stats()
        eta = "?" if stats.eta_seconds is None else f"{stats.eta_seconds:.1f} с"
        print(
            f"Прогресс: {stats.progress_percent:.1f}% "
            f"({stats.total_pages}/{stats.target_pages}) | "
            f"Скорость: {stats.average_speed:.2f} стр/с | "
            f"Осталось: {eta} | Активно: {stats.active_tasks}",
            flush=True,
        )

    async def close(self) -> None:
        await self.sitemap_parser.close()
        await super().close()
