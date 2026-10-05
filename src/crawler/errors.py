"""Ошибки загрузки и разбора страниц."""


class CrawlerError(Exception):
    def __init__(
        self,
        message: str,
        *,
        url: str = "",
        status: int | None = None,
        content: str = "",
        location: str | None = None,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.status = status
        self.content = content
        self.location = location


class TransientError(CrawlerError):
    """Временная HTTP-ошибка или таймаут."""


class PermanentError(CrawlerError):
    """Ошибка, которую повторный запрос не исправит."""


class NetworkError(CrawlerError):
    """Ошибка соединения, DNS или передачи ответа."""


class ParseError(CrawlerError):
    """Ошибка разбора HTML."""
