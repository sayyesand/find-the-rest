from app.benchmark import benchmark_summary, run_benchmark


def test_adversarial_benchmark_passes_all_cases():
    results = run_benchmark()
    failures = [case for case in results if not case.passed]
    assert len(results) >= 14
    assert failures == []


def test_benchmark_summary_has_category_breakdown():
    data = benchmark_summary()
    assert data["passed"] == data["total"]
    assert data["pass_rate"] == 1.0
    assert {"false_positive", "positive", "repost", "provenance", "ordering", "no_answer"} <= set(data["categories"])
    assert all(bucket["pass_rate"] == 1.0 for bucket in data["categories"].values())


def test_benchmark_endpoint_is_wired():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    main = (root / "backend/app/main.py").read_text()
    models = (root / "backend/app/models.py").read_text()
    assert '@app.get("/v1/benchmark"' in main
    assert "BenchmarkSummaryResponse" in models
