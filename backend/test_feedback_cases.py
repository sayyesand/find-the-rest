import json
from pathlib import Path

from app.feedback_cases import make_case, record_case, summary


def test_feedback_case_excludes_raw_urls_and_content():
    payload = {
        "search_id": "search-123",
        "verdict": "wrong",
        "best_match_url": "https://example.com/private/path?token=secret",
        "source_platform": "tiktok",
        "confidence": .82,
        "search_intent": "continue_story",
        "result_state": "continuation_found",
        "confidence_grade": "high",
        "evidence_family_count": 5,
        "strong_evidence_family_count": 3,
        "transcript": "never store this",
        "visible_text": "never store this either",
        "title": "private title",
        "creator": "private creator",
    }
    case = make_case(payload)
    serialized = json.dumps(case)
    assert "private/path" not in serialized
    assert "token=secret" not in serialized
    assert "never store this" not in serialized
    assert "private title" not in serialized
    assert "private creator" not in serialized
    assert case["best_match_fingerprint"]
    assert len(case["best_match_fingerprint"]) == 16
    assert case["confidence_bucket"] == "80-100"


def test_feedback_summary_surfaces_high_confidence_wrong_patterns(monkeypatch, tmp_path):
    path = tmp_path / "cases.jsonl"
    monkeypatch.setenv("FINDREST_FEEDBACK_CASES_PATH", str(path))

    base = {
        "source_platform": "youtube",
        "search_intent": "continue_story",
        "result_state": "continuation_found",
        "evidence_family_count": 4,
        "strong_evidence_family_count": 2,
    }
    record_case({**base, "search_id": "a", "verdict": "wrong", "confidence": .84, "confidence_grade": "high"})
    record_case({**base, "search_id": "b", "verdict": "wrong", "confidence": .72, "confidence_grade": "moderate"})
    record_case({**base, "search_id": "c", "verdict": "correct", "confidence": .75, "confidence_grade": "moderate"})

    data = summary()
    assert data["cases"] == 3
    assert data["failure_cases"] == 2
    assert data["high_confidence_wrong"] == 2
    assert data["verdict_counts"]["wrong"] == 2
    assert data["top_failure_patterns"]


def test_feedback_case_retention_is_bounded(monkeypatch, tmp_path):
    path = tmp_path / "cases.jsonl"
    monkeypatch.setenv("FINDREST_FEEDBACK_CASES_PATH", str(path))
    monkeypatch.setenv("FINDREST_FEEDBACK_CASES_MAX", "50")
    for i in range(130):
        record_case({
            "search_id": f"s-{i}",
            "verdict": "wrong",
            "confidence": .5,
            "confidence_grade": "tentative",
        })
    lines = path.read_text().splitlines()
    assert len(lines) <= 100
