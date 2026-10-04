import asyncio
import pytest

from src.concurrency.semaphore_manager import (
    SemaphoreManager,
)


@pytest.mark.parametrize(
    "global_limit",
    [
        0,
        -1,
        1.5,
        True,
    ],
)
def test_init_rejects_invalid_global_limit(
    global_limit,
) -> None:
    with pytest.raises(
        ValueError,
        match="Глобальный лимит",
    ):
        SemaphoreManager(
            global_limit=global_limit,
            per_domain_limit=1,
        )


@pytest.mark.parametrize(
    "per_domain_limit",
    [
        0,
        -1,
        1.5,
        True,
    ],
)
def test_init_rejects_invalid_domain_limit(
    per_domain_limit,
) -> None:
    with pytest.raises(
        ValueError,
        match="Доменный лимит",
    ):
        SemaphoreManager(
            global_limit=2,
            per_domain_limit=per_domain_limit,
        )


@pytest.mark.parametrize(
    "url",
    [
        "",
        "relative-page",
        "mailto:user@example.com",
    ],
)
async def test_limit_rejects_invalid_url(
    url: str,
) -> None:
    manager = SemaphoreManager(
        global_limit=2,
        per_domain_limit=1,
    )

    with pytest.raises(ValueError):
        async with manager.limit(url):
            pass


async def test_global_limit_restricts_active_tasks(
) -> None:
    manager = SemaphoreManager(
        global_limit=2,
        per_domain_limit=5,
    )
    active_tasks = 0
    peak_active_tasks = 0

    async def worker(index: int) -> None:
        nonlocal active_tasks
        nonlocal peak_active_tasks

        url = (
            f"https://domain-{index}.example.com/page"
        )

        async with manager.limit(url):
            active_tasks += 1
            peak_active_tasks = max(
                peak_active_tasks,
                active_tasks,
            )
            await asyncio.sleep(0.02)
            active_tasks -= 1

    await asyncio.gather(
        *(worker(index) for index in range(5))
    )

    assert peak_active_tasks == 2
    assert manager.get_stats()["peak_active"] == 2
    assert manager.get_stats()["active"] == 0


async def test_domain_limit_restricts_same_domain(
) -> None:
    manager = SemaphoreManager(
        global_limit=5,
        per_domain_limit=2,
    )
    active_tasks = 0
    peak_active_tasks = 0

    async def worker(index: int) -> None:
        nonlocal active_tasks
        nonlocal peak_active_tasks

        url = (
            f"https://example.com/page/{index}"
        )

        async with manager.limit(url):
            active_tasks += 1
            peak_active_tasks = max(
                peak_active_tasks,
                active_tasks,
            )
            await asyncio.sleep(0.02)
            active_tasks -= 1

    await asyncio.gather(
        *(worker(index) for index in range(5))
    )

    stats = manager.get_stats()

    assert peak_active_tasks == 2
    assert stats["peak_by_domain"] == {
        "example.com": 2,
    }
    assert stats["active"] == 0
    assert stats["active_by_domain"] == {}


async def test_different_domains_run_concurrently(
) -> None:
    manager = SemaphoreManager(
        global_limit=2,
        per_domain_limit=1,
    )
    release_tasks = asyncio.Event()
    both_tasks_active = asyncio.Event()

    async def worker(url: str) -> None:
        async with manager.limit(url):
            if manager.get_stats()["active"] == 2:
                both_tasks_active.set()

            await release_tasks.wait()

    tasks = [
        asyncio.create_task(
            worker("https://first.example.com")
        ),
        asyncio.create_task(
            worker("https://second.example.com")
        ),
    ]

    try:
        await asyncio.wait_for(
            both_tasks_active.wait(),
            timeout=1,
        )

        stats = manager.get_stats()

        assert stats["active"] == 2
        assert stats["active_by_domain"] == {
            "first.example.com": 1,
            "second.example.com": 1,
        }
    finally:
        release_tasks.set()
        await asyncio.gather(*tasks)


async def test_stats_track_active_task() -> None:
    manager = SemaphoreManager(
        global_limit=3,
        per_domain_limit=2,
    )

    async with manager.limit(
        "https://example.com/page"
    ):
        assert manager.get_stats() == {
            "active": 1,
            "peak_active": 1,
            "active_by_domain": {
                "example.com": 1,
            },
            "peak_by_domain": {
                "example.com": 1,
            },
        }

    assert manager.get_stats() == {
        "active": 0,
        "peak_active": 1,
        "active_by_domain": {},
        "peak_by_domain": {
            "example.com": 1,
        },
    }


async def test_limit_releases_semaphores_after_error(
) -> None:
    manager = SemaphoreManager(
        global_limit=1,
        per_domain_limit=1,
    )
    url = "https://example.com/page"

    with pytest.raises(
        RuntimeError,
        match="Ошибка задачи",
    ):
        async with manager.limit(url):
            raise RuntimeError("Ошибка задачи")

    assert manager.get_stats()["active"] == 0
    assert (
        manager.get_stats()["active_by_domain"]
        == {}
    )

    async def acquire_again() -> None:
        async with manager.limit(url):
            assert (
                manager.get_stats()["active"]
                == 1
            )

    await asyncio.wait_for(
        acquire_again(),
        timeout=1,
    )
