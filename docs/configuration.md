# Конфигурация и запуск

Файл [config.example.json](../config.example.json) показывает полную JSON-конфигурацию. Пути к файлам интерпретируются относительно текущего рабочего каталога, поэтому команды ниже следует запускать из корня проекта.

| Раздел | Назначение |
| --- | --- |
| `start_urls` | Стартовые HTTP/HTTPS-страницы |
| `sitemaps` | Обычные или индексные sitemap.xml |
| `crawler` | Параллельность, глубина, частота, robots.txt, таймауты и повторы; параметры `AsyncCrawler` |
| `crawl` | `max_pages`, `same_domain_only`, `include_patterns`, `exclude_patterns`, `show_progress` |
| `storage` | `format`: `jsonl`, `json`, `csv`, `sqlite`; `path`; размер буфера или пакета |
| `logging` | `path`, `level`, `max_bytes`, `backup_count` |
| `reports` | Пути `json` и `html` для итоговой статистики |

Нужен хотя бы один стартовый URL или доступный sitemap. `AdvancedCrawler.from_config(path)` читает JSON и создаёт краулер со всеми компонентами. `await crawler.crawl()` использует URL и параметры файла; `await crawler.close()` сбрасывает хранилище и закрывает соединения.

```bash
python crawler.py --config config.example.json
python crawler.py --urls https://example.com --max-pages 100 --max-depth 2 --output output/pages.jsonl
python crawler.py --sitemaps https://example.com/sitemap.xml --rate-limit 2 --respect-robots --stats-json output/stats.json --html-report output/report.html
```

CLI поддерживает `--urls`, `--sitemaps`, `--max-pages`, `--max-depth`, `--output`, `--config`, `--respect-robots` / `--no-respect-robots`, `--rate-limit`, `--stats-json` и `--html-report`. Указанные в CLI значения перекрывают соответствующие поля JSON. Формат `--output` определяется расширением: `.jsonl`, `.json`, `.csv`, `.db` или `.sqlite`. HTML-отчёт содержит только статистику; страницы сохраняются отдельно через `storage` или `--output`.

Пример кода находится в [examples/run_crawler.py](../examples/run_crawler.py). Его можно запустить командой `python -m examples.run_crawler`.
