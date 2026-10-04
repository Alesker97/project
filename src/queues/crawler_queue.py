import asyncio
from itertools import count


class CrawlerQueue:
    def __init__(self) -> None:
        self._queue: asyncio.PriorityQueue[
            tuple[int, int, str]
        ] = asyncio.PriorityQueue()
        self._sequence = count()
        self._known_urls: set[str] = set()
        self._active_urls: set[str] = set()
        self._processed_urls: set[str] = set()
        self._failed_urls: dict[str, str] = {}

    def add_url(
        self,
        url: str,
        priority: int = 0,
    ) -> None:
        if not isinstance(url, str) or not url.strip():
            raise ValueError(
                "URL должен быть непустой строкой."
            )

        if (
            isinstance(priority, bool)
            or not isinstance(priority, int)
        ):
            raise ValueError(
                "Приоритет должен быть целым числом."
            )

        normalized_url = url.strip()

        if normalized_url in self._known_urls:
            return

        self._known_urls.add(normalized_url)
        self._queue.put_nowait(
            (
                -priority,
                next(self._sequence),
                normalized_url,
            )
        )

    async def get_next(self) -> str | None:
        try:
            _, _, url = self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

        self._active_urls.add(url)
        return url

    def mark_processed(
        self,
        url: str,
    ) -> None:
        if url not in self._active_urls:
            return

        self._active_urls.remove(url)
        self._processed_urls.add(url)
        self._queue.task_done()

    def mark_failed(
        self,
        url: str,
        error: str,
    ) -> None:
        if url not in self._active_urls:
            return

        self._active_urls.remove(url)
        self._failed_urls[url] = error
        self._queue.task_done()

    def get_stats(self) -> dict[str, int]:
        return {
            "queued": self._queue.qsize(),
            "active": len(self._active_urls),
            "processed": len(
                self._processed_urls
            ),
            "failed": len(self._failed_urls),
            "total": len(self._known_urls),
        }
