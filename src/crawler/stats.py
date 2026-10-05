"""Сводная статистика обхода и самостоятельные отчёты."""

import html
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class CrawlerStats:
    total_pages: int
    successful: int
    failed: int
    average_speed: float
    status_codes: dict[int, int]
    top_domains: list[tuple[str, int]]
    run_time: float
    active_tasks: int
    queued: int
    target_pages: int
    progress_percent: float
    eta_seconds: float | None

    @classmethod
    def from_crawler(
        cls,
        crawler,
        *,
        run_time: float,
        target_pages: int,
        finished: bool,
    ) -> "CrawlerStats":
        successful = len(crawler.processed_urls)
        failed = len(crawler.failed_urls)
        total = successful + failed
        domains = Counter(
            urlsplit(url).hostname or ""
            for url in crawler.visited_urls
        )
        statuses = Counter(
            status for url, (status, _) in crawler._page_response_details.items()
            if url in crawler.visited_urls
        )
        speed = total / run_time if run_time > 0 else 0.0
        remaining = max(target_pages - total, 0)
        return cls(
            total_pages=total,
            successful=successful,
            failed=failed,
            average_speed=speed,
            status_codes=dict(sorted(statuses.items())),
            top_domains=sorted(domains.items(), key=lambda item: (-item[1], item[0]))[:10],
            run_time=run_time,
            active_tasks=crawler._queue.get_stats()["active"],
            queued=crawler._queue.get_stats()["queued"],
            target_pages=target_pages,
            progress_percent=(100.0 if finished else min(total / target_pages * 100, 100.0)),
            eta_seconds=(0.0 if finished else remaining / speed if speed > 0 else None),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def export_to_json(self, filename: str | Path) -> None:
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def export_to_html_report(self, filename: str | Path) -> None:
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        summary = [
            ("Обработано", self.total_pages), ("Успешно", self.successful),
            ("Ошибок", self.failed), ("Скорость, стр/с", f"{self.average_speed:.2f}"),
            ("Время, с", f"{self.run_time:.2f}"),
        ]
        cards = "".join(
            f"<div class='card'><strong>{html.escape(label)}</strong><span>{value}</span></div>"
            for label, value in summary
        )
        def rows(items, maximum):
            return "".join(
                "<tr><th scope='row'>{}</th><td>{}</td><td><div class='bar' style='width:{:.1f}%'></div></td></tr>".format(
                    html.escape(str(name)), count, count / max(maximum, 1) * 100,
                )
                for name, count in items
            )
        status_rows = rows(self.status_codes.items(), max(self.status_codes.values(), default=0))
        domain_rows = rows(self.top_domains, max((count for _, count in self.top_domains), default=0))
        document = f"""<!doctype html>
<html lang='ru'><head><meta charset='utf-8'><title>Отчёт краулера</title>
<style>body{{font:16px system-ui;max-width:960px;margin:2rem auto;padding:0 1rem;color:#182335}}
h1,h2{{color:#123a64}}.cards{{display:flex;flex-wrap:wrap;gap:1rem}}
.card{{padding:1rem;border:1px solid #ccd7e1;border-radius:.5rem;min-width:130px}}
.card strong,.card span{{display:block}}.card span{{font-size:1.5rem}}
table{{border-collapse:collapse;width:100%;margin-bottom:2rem}}th,td{{padding:.5rem;border-bottom:1px solid #ddd;text-align:left}}
td:last-child{{width:40%}}.bar{{height:1rem;background:#3279bd;border-radius:.25rem}}</style></head>
<body><h1>Отчёт краулера</h1><div class='cards'>{cards}</div>
<h2>HTTP-статусы</h2><table><thead><tr><th>Статус</th><th>Страниц</th><th>Доля от максимума</th></tr></thead><tbody>{status_rows}</tbody></table>
<h2>Домены</h2><table><thead><tr><th>Домен</th><th>Страниц</th><th>Доля от максимума</th></tr></thead><tbody>{domain_rows}</tbody></table>
</body></html>"""
        path.write_text(document, encoding="utf-8")
