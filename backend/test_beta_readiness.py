from pathlib import Path

from app.benchmark import benchmark_summary
from app.beta_readiness import readiness_summary


def test_expanded_adversarial_benchmark_passes_all_cases():
    summary = benchmark_summary()
    assert summary["total"] >= 23
    assert summary["passed"] == summary["total"]
    assert summary["pass_rate"] == 1.0


def test_beta_readiness_requires_critical_configuration(monkeypatch):
    monkeypatch.setenv("FIND_THE_REST_API_KEY", "short")
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    data = readiness_summary()
    assert data["beta_ready"] is False
    critical = {g["gate_id"]: g for g in data["gates"] if g["critical"]}
    assert critical["adversarial-benchmark"]["passed"] is True
    assert critical["api-auth"]["passed"] is False
    assert critical["public-search"]["passed"] is False


def test_beta_readiness_can_clear_critical_gates(monkeypatch):
    monkeypatch.setenv("FIND_THE_REST_API_KEY", "this-is-a-strong-beta-key")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "configured")
    data = readiness_summary()
    assert data["critical_passed"] == data["critical_total"]
    assert data["beta_ready"] is True


def test_optional_provider_gates_do_not_block_core_beta_readiness(monkeypatch):
    monkeypatch.setenv("FIND_THE_REST_API_KEY", "this-is-a-strong-beta-key")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "configured")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("FINDREST_REVERSE_IMAGE_ENDPOINT", raising=False)
    monkeypatch.delenv("FINDREST_CANDIDATE_MEDIA_ENDPOINT", raising=False)
    monkeypatch.delenv("FINDREST_VISION_CLUES_ENDPOINT", raising=False)
    data = readiness_summary()
    assert data["beta_ready"] is True
    assert data["passed"] < data["total"]


def test_beta_readiness_endpoint_is_protected():
    root = Path(__file__).resolve().parents[1]
    main = (root / "backend/app/main.py").read_text()
    marker = '@app.get("/v1/beta-readiness"'
    assert marker in main
    block = main[main.index(marker):main.index(marker)+300]
    assert "Depends(require_api_key)" in block
