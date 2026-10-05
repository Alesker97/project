from benchmarks.crawler_benchmark import run_benchmark


async def test_benchmark_processes_same_pages(tmp_path):
    report = tmp_path / "benchmark.json"
    rows = await run_benchmark((10,), output=report)
    assert len(rows) == 1
    assert rows[0]["pages"] == 10
    assert rows[0]["sync_seconds"] > 0
    assert rows[0]["async_seconds"] > 0
    assert rows[0]["async_peak_bytes"] > 0
    assert report.exists()
