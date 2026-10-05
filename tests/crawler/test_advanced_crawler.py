import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from aiohttp import web

from src.cli import build_parser, run, settings_from_args
from src.crawler.advanced_crawler import AdvancedCrawler
from src.crawler.logging_config import configure_logging


@pytest.fixture
async def local_site():
    async def handle(request):
        base = f"http://{request.host}"
        if request.path == "/sitemap.xml":
            return web.Response(
                text=f"<urlset><url><loc>{base}/a</loc></url><url><loc>{base}/missing</loc></url></urlset>",
                content_type="application/xml",
            )
        if request.path == "/missing":
            return web.Response(status=404)
        return web.Response(text="<title>Страница</title>", content_type="text/html")

    app = web.Application()
    app.router.add_get("/{path:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", 0).start()
        yield f"http://127.0.0.1:{runner.addresses[0][1]}"
    finally:
        await runner.cleanup()


async def test_advanced_crawler_uses_sitemap_and_exports_reports(local_site, tmp_path):
    config = {
        "start_urls": [],
        "sitemaps": [f"{local_site}/sitemap.xml"],
        "crawler": {"respect_robots": False, "requests_per_second": 1000, "max_retries": 0},
        "crawl": {"max_pages": 10, "show_progress": False},
        "storage": {"format": "jsonl", "path": str(tmp_path / "pages.jsonl")},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    crawler = AdvancedCrawler.from_config(config_path)
    try:
        pages = await crawler.crawl()
        assert list(pages) == [f"{local_site}/a"]
        stats = crawler.get_stats()
        assert stats.total_pages == 2
        assert stats.successful == 1
        assert stats.failed == 1
        assert stats.status_codes == {200: 1, 404: 1}
        assert stats.top_domains == [("127.0.0.1", 2)]
        assert stats.progress_percent == 100
        assert stats.average_speed > 0
        assert stats.run_time > 0
        assert crawler.get_storage_stats()["saved"] == 1
        json_path = tmp_path / "reports" / "stats.json"
        html_path = tmp_path / "reports" / "stats.html"
        crawler.export_to_json(json_path)
        crawler.export_to_html_report(html_path)
        assert json.loads(json_path.read_text(encoding="utf-8"))["status_codes"] == {"200": 1, "404": 1}
        report = html_path.read_text(encoding="utf-8")
        assert "HTTP-статусы" in report and "127.0.0.1" in report
        assert "class='bar'" in report
    finally:
        await crawler.close()


async def test_cli_options_override_config_and_run(local_site, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "start_urls": [f"{local_site}/missing"],
        "crawler": {"respect_robots": False, "requests_per_second": 1000},
        "crawl": {"max_pages": 1, "show_progress": False},
    }), encoding="utf-8")
    args = build_parser().parse_args([
        "--config", str(config_path), "--urls", f"{local_site}/a",
        "--max-pages", "2", "--max-depth", "0",
        "--output", str(tmp_path / "pages.csv"), "--rate-limit", "1000",
        "--no-respect-robots", "--stats-json", str(tmp_path / "stats.json"),
    ])
    settings = settings_from_args(args)
    assert settings["start_urls"] == [f"{local_site}/a"]
    assert settings["crawler"]["max_depth"] == 0
    assert settings["storage"]["format"] == "csv"
    stats = await run(settings)
    assert stats["successful"] == 1
    assert (tmp_path / "pages.csv").exists()
    assert (tmp_path / "stats.json").exists()


def test_json_logging_rotates_and_has_timestamp(tmp_path):
    path = tmp_path / "crawler.log"
    root = logging.getLogger()
    previous_level = root.level
    try:
        configure_logging(path, level="INFO", max_bytes=240, backup_count=2)
        for index in range(12):
            logging.getLogger("crawler.test").info("message %s", index, extra={"url": "https://example.test"})
        assert path.exists()
        assert Path(f"{path}.1").exists()
        row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        assert {"timestamp", "level", "logger", "message", "url"} <= set(row)
    finally:
        for handler in list(root.handlers):
            if getattr(handler, "_crawler_managed", False):
                root.removeHandler(handler)
                handler.close()
        root.setLevel(previous_level)


def test_config_rejects_unknown_options():
    with pytest.raises(ValueError, match="Неизвестные"):
        AdvancedCrawler.from_settings({"wrong_key": True})


def test_public_import_and_cli_help():
    from crawler import AdvancedCrawler as PublicCrawler

    assert PublicCrawler is AdvancedCrawler
    result = subprocess.run(
        [sys.executable, "crawler.py", "--help"],
        capture_output=True, text=True, check=True,
    )
    assert "--urls" in result.stdout
    assert "--config" in result.stdout


async def test_cli_process_crawls_and_writes_json(local_site, tmp_path):
    output = tmp_path / "pages.json"
    process = await asyncio.create_subprocess_exec(
        sys.executable, "crawler.py", "--urls", f"{local_site}/a",
        "--max-pages", "1", "--output", str(output),
        "--no-respect-robots", "--rate-limit", "1000",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    stdout, stderr = await process.communicate()
    assert process.returncode == 0, stderr.decode("utf-8", errors="replace")
    assert "успешно: 1" in stdout.decode("utf-8", errors="replace")
    assert len(json.loads(output.read_text(encoding="utf-8"))) == 1
