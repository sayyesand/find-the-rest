from app.watch_store import create_watch


def test_same_source_can_have_different_watch_intents(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_WATCH_DB_PATH", str(tmp_path / "watches.sqlite3"))
    a = create_watch("https://example.com/story", "web", intent="continue_story")
    b = create_watch("https://example.com/story", "web", intent="full_original")
    assert a["watch_id"] != b["watch_id"]
    assert a["intent"] == "continue_story"
    assert b["intent"] == "full_original"


def test_duplicate_watch_same_intent_is_reused(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_WATCH_DB_PATH", str(tmp_path / "watches.sqlite3"))
    a = create_watch("https://example.com/story", "web", intent="original_source")
    b = create_watch("https://example.com/story?utm_source=x", "web", intent="original_source")
    assert a["watch_id"] == b["watch_id"]
