import json

from app.diagnostics import record_event, recent_events, summary


def test_diagnostics_drops_raw_user_content(monkeypatch, tmp_path):
    path = tmp_path / "diag.jsonl"
    monkeypatch.setenv("FINDREST_DIAGNOSTICS_PATH", str(path))
    record_event(
        "analyze",
        success=True,
        source_platform="instagram",
        result_state="continuation_found",
        confidence=.81,
        url="https://secret.example/post",
        transcript="private spoken words",
        visible_text="private OCR",
        device_token="super-secret-token",
        evidence_paths=["story_fingerprint", "ending"],
    )
    raw = path.read_text()
    assert "secret.example" not in raw
    assert "private spoken words" not in raw
    assert "private OCR" not in raw
    assert "super-secret-token" not in raw
    event = json.loads(raw)
    assert event["source_platform"] == "instagram"
    assert event["evidence_paths"] == ["story_fingerprint", "ending"]


def test_diagnostics_summary_reports_quality_metrics(monkeypatch, tmp_path):
    path = tmp_path / "diag.jsonl"
    monkeypatch.setenv("FINDREST_DIAGNOSTICS_PATH", str(path))
    record_event("analyze", success=True, result_state="continuation_found", source_platform="youtube", latency_ms=100, evidence_paths=["story_fingerprint"])
    record_event("analyze", success=True, result_state="no_verified_match", source_platform="tiktok", latency_ms=300, evidence_paths=["ending"])
    record_event("media_discovery", success=True, found=True, latency_ms=200, evidence_paths=["ocr"])
    data = summary()
    assert data["events"] == 3
    assert data["searches"] == 3
    assert data["credible_results"] == 2
    assert data["credible_result_rate"] == round(2/3, 4)
    assert data["latency_ms"]["p50"] == 200
    assert data["evidence_path_counts"]["ocr"] == 1


def test_diagnostics_event_retention_is_bounded(monkeypatch, tmp_path):
    path = tmp_path / "diag.jsonl"
    monkeypatch.setenv("FINDREST_DIAGNOSTICS_PATH", str(path))
    monkeypatch.setenv("FINDREST_DIAGNOSTICS_MAX_EVENTS", "50")
    for i in range(105):
        record_event("analyze", success=True, latency_ms=i)
    events = recent_events()
    assert len(events) <= 50
