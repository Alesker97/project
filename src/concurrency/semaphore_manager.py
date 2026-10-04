import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse


class SemaphoreManager:
    def __init__(
        self,
        global_limit: int,
        per_domain_limit: int,
    ) -> None:
        self._validate_limit(
            global_limit,
            "Глобальный лимит",
        )
        self._validate_limit(
            per_domain_limit,
            "Доменный лимит",
        )

        self._global_limit = global_limit
        self._per_domain_limit = per_domain_limit
        self._global_semaphore = asyncio.Semaphore(
            global_limit
        )
        self._domain_semaphores: dict[
            str,
            asyncio.Semaphore,
        ] = {}
        self._active_tasks = 0
        self._peak_active_tasks = 0
        self._active_by_domain: dict[str, int] = {}
        self._peak_by_domain: dict[str, int] = {}

    @asynccontextmanager
    async def limit(
        self,
        url: str,
    ) -> AsyncIterator[None]:
        domain = self._extract_domain(url)
        domain_semaphore = self._get_domain_semaphore(
            domain
        )

        await domain_semaphore.acquire()

        try:
            await self._global_semaphore.acquire()

            try:
                self._register_task_start(domain)
                yield
            finally:
                self._register_task_end(domain)
                self._global_semaphore.release()
        finally:
            domain_semaphore.release()

    def get_stats(self) -> dict[str, object]:
        return {
            "active": self._active_tasks,
            "peak_active": self._peak_active_tasks,
            "active_by_domain": dict(
                self._active_by_domain
            ),
            "peak_by_domain": dict(
                self._peak_by_domain
            ),
        }

    def _get_domain_semaphore(
        self,
        domain: str,
    ) -> asyncio.Semaphore:
        if domain not in self._domain_semaphores:
            self._domain_semaphores[domain] = (
                asyncio.Semaphore(
                    self._per_domain_limit
                )
            )

        return self._domain_semaphores[domain]

    def _register_task_start(
        self,
        domain: str,
    ) -> None:
        self._active_tasks += 1
        self._peak_active_tasks = max(
            self._peak_active_tasks,
            self._active_tasks,
        )

        domain_active = (
            self._active_by_domain.get(domain, 0)
            + 1
        )
        self._active_by_domain[domain] = (
            domain_active
        )
        self._peak_by_domain[domain] = max(
            self._peak_by_domain.get(domain, 0),
            domain_active,
        )

    def _register_task_end(
        self,
        domain: str,
    ) -> None:
        self._active_tasks -= 1
        domain_active = (
            self._active_by_domain[domain] - 1
        )

        if domain_active == 0:
            del self._active_by_domain[domain]
        else:
            self._active_by_domain[domain] = (
                domain_active
            )

    @staticmethod
    def _extract_domain(url: str) -> str:
        if not isinstance(url, str) or not url.strip():
            raise ValueError(
                "URL должен быть непустой строкой."
            )

        domain = urlparse(url).hostname

        if domain is None:
            raise ValueError(
                "URL должен содержать корректный домен."
            )

        return domain.lower()

    @staticmethod
    def _validate_limit(
        value: int,
        name: str,
    ) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
        ):
            raise ValueError(
                f"{name} должен быть положительным "
                "целым числом."
            )
