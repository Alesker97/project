import json
from pathlib import Path

from src.main import demonstrate_politeness, save_crawl_results


async def test_save_crawl_results_creates_json(
    tmp_path: Path,
) -> None:
    file_path = (
        tmp_path
        / "output"
        / "crawl_results.json"
    )
    results = {
        "https://example.com": {
            "url": "https://example.com",
            "title": "Example Domain",
            "text": "Example text",
            "links": [],
        }
    }

    await save_crawl_results(
        results,
        file_path,
    )

    assert file_path.exists()

    saved_data = json.loads(
        file_path.read_text(encoding="utf-8")
    )

    assert saved_data == results


async def test_politeness_demo_blocks_private_url_and_recovers_from_errors(capsys):
    await demonstrate_politeness()
    output = capsys.readouterr().out
    assert "Успешных страниц: 3" in output
    assert "Заблокировано URL: 1; повторов: 2" in output
    assert "Запросов к /private на сервере: 0" in output
    assert "Средняя задержка:" in output
