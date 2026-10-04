import pytest

from src.queues.crawler_queue import CrawlerQueue


async def test_get_next_returns_none_for_empty_queue(
) -> None:
    queue = CrawlerQueue()

    result = await queue.get_next()

    assert result is None


async def test_queue_returns_high_priority_first(
) -> None:
    queue = CrawlerQueue()
    queue.add_url(
        "https://example.com/low",
        priority=1,
    )
    queue.add_url(
        "https://example.com/high",
        priority=10,
    )
    queue.add_url(
        "https://example.com/normal",
        priority=5,
    )

    first = await queue.get_next()
    second = await queue.get_next()
    third = await queue.get_next()

    assert first == "https://example.com/high"
    assert second == "https://example.com/normal"
    assert third == "https://example.com/low"


async def test_queue_uses_fifo_for_equal_priority(
) -> None:
    queue = CrawlerQueue()
    queue.add_url(
        "https://example.com/first",
        priority=5,
    )
    queue.add_url(
        "https://example.com/second",
        priority=5,
    )
    queue.add_url(
        "https://example.com/third",
        priority=5,
    )

    first = await queue.get_next()
    second = await queue.get_next()
    third = await queue.get_next()

    assert first == "https://example.com/first"
    assert second == "https://example.com/second"
    assert third == "https://example.com/third"


async def test_queue_ignores_duplicate_urls() -> None:
    queue = CrawlerQueue()

    queue.add_url("https://example.com/page")
    queue.add_url("https://example.com/page")
    queue.add_url("  https://example.com/page  ")

    first = await queue.get_next()
    second = await queue.get_next()

    assert first == "https://example.com/page"
    assert second is None
    assert queue.get_stats()["total"] == 1


async def test_mark_processed_updates_stats() -> None:
    queue = CrawlerQueue()
    url = "https://example.com/success"

    queue.add_url(url)
    selected_url = await queue.get_next()

    assert selected_url == url
    assert queue.get_stats() == {
        "queued": 0,
        "active": 1,
        "processed": 0,
        "failed": 0,
        "total": 1,
    }

    queue.mark_processed(url)

    assert queue.get_stats() == {
        "queued": 0,
        "active": 0,
        "processed": 1,
        "failed": 0,
        "total": 1,
    }


async def test_mark_failed_updates_stats() -> None:
    queue = CrawlerQueue()
    url = "https://example.com/error"

    queue.add_url(url)
    selected_url = await queue.get_next()

    assert selected_url == url

    queue.mark_failed(
        url,
        "HTTP 500",
    )

    assert queue.get_stats() == {
        "queued": 0,
        "active": 0,
        "processed": 0,
        "failed": 1,
        "total": 1,
    }
    assert queue._failed_urls == {
        url: "HTTP 500",
    }


async def test_stats_include_every_queue_state() -> None:
    queue = CrawlerQueue()
    processed_url = "https://example.com/processed"
    failed_url = "https://example.com/failed"
    queued_url = "https://example.com/queued"
    active_url = "https://example.com/active"

    queue.add_url(processed_url)
    queue.add_url(failed_url)
    queue.add_url(queued_url)
    queue.add_url(active_url)

    selected_url = await queue.get_next()
    assert selected_url == processed_url
    queue.mark_processed(processed_url)

    selected_url = await queue.get_next()
    assert selected_url == failed_url
    queue.mark_failed(
        failed_url,
        "Ошибка загрузки",
    )

    selected_url = await queue.get_next()
    assert selected_url == queued_url

    assert queue.get_stats() == {
        "queued": 1,
        "active": 1,
        "processed": 1,
        "failed": 1,
        "total": 4,
    }


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "   ",
    ],
)
def test_add_url_rejects_invalid_url(url) -> None:
    queue = CrawlerQueue()

    with pytest.raises(
        ValueError,
        match="URL должен быть непустой строкой",
    ):
        queue.add_url(url)


@pytest.mark.parametrize(
    "priority",
    [
        1.5,
        "1",
        True,
    ],
)
def test_add_url_rejects_invalid_priority(
    priority,
) -> None:
    queue = CrawlerQueue()

    with pytest.raises(
        ValueError,
        match="Приоритет должен быть целым числом",
    ):
        queue.add_url(
            "https://example.com",
            priority=priority,
        )
