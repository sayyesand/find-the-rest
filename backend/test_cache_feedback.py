import json
from pathlib import Path

from app.cache import canonical_key, get, put
from app.feedback import record_feedback


def test_cache_round_trip():
    key = canonical_key("test", "https://example.com/video|web")
    put(key, {"ok": True})
    assert get(key) == {"ok": True}


def test_cache_key_is_stable_and_does_not_expose_payload():
    payload = "https://example.com/private-looking-path?token=secret"
    a = canonical_key("analyze", payload)
    b = canonical_key("analyze", payload)
    assert a == b
    assert "secret" not in a
    assert payload not in a


def test_feedback_store_excludes_raw_media_and_text(monkeypatch, tmp_path):
    path = tmp_path / "feedback.jsonl"
    monkeypatch.setenv("FINDREST_FEEDBACK_PATH", str(path))
    record_feedback({
        "search_id": "abc123",
        "verdict": "wrong",
        "best_match_url": "https://example.com/result",
        "source_platform": "web",
        "confidence": .42,
        "transcript": "this must not be stored",
        "ocr_text": "also must not be stored",
        "raw_media": "never",
    })
    data = json.loads(path.read_text().strip())
    assert data["search_id"] == "abc123"
    assert data["verdict"] == "wrong"
    assert "transcript" not in data
    assert "ocr_text" not in data
    assert "raw_media" not in data
