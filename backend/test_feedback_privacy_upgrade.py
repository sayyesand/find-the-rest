import json
from pathlib import Path

from app.feedback import record_feedback


def test_legacy_feedback_store_hashes_best_match_url(monkeypatch, tmp_path):
    path = tmp_path / "feedback.jsonl"
    monkeypatch.setenv("FINDREST_FEEDBACK_PATH", str(path))
    record_feedback({
        "search_id": "abc123",
        "verdict": "wrong",
        "best_match_url": "https://example.com/result?secret=yes",
        "source_platform": "web",
        "confidence": .42,
    })
    data = json.loads(path.read_text().strip())
    assert "best_match_url" not in data
    assert data["best_match_fingerprint"]
    assert "secret=yes" not in path.read_text()


def test_feedback_summary_endpoint_is_protected_and_wired():
    root = Path(__file__).resolve().parents[1]
    main = (root / "backend/app/main.py").read_text()
    assert '@app.get("/v1/feedback-summary"' in main
    assert "Depends(require_api_key)" in main[main.index('@app.get("/v1/feedback-summary"'):]


def test_ios_feedback_sends_regression_quality_context():
    root = Path(__file__).resolve().parents[1]
    content = (root / "ios/FindTheRest/ContentView.swift").read_text()
    models = (root / "ios/FindTheRest/APIModels.swift").read_text()
    assert "searchIntent: currentSearchIntent" in content
    assert "resultState: currentResultState" in content
    assert "confidenceGrade: currentConfidenceGrade" in content
    assert "evidenceFamilyCount: currentEvidenceFamilyCount" in content
    assert "strongEvidenceFamilyCount: currentStrongEvidenceFamilyCount" in content
    assert 'case searchIntent = "search_intent"' in models
