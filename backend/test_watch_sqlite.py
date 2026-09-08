import json
import sqlite3
from pathlib import Path

from app.watch_store import create_watch, get_watch, list_active, storage_info


def test_sqlite_watch_store_created(monkeypatch, tmp_path):
    path = tmp_path / "watches.sqlite3"
    monkeypatch.setenv("FINDREST_WATCH_DB_PATH", str(path))
    w = create_watch("https://example.com/story?utm_source=test", "web")
    assert path.exists()
    assert w["source_url"] == "https://example.com/story"
    assert storage_info()["backend"] == "sqlite"
    with sqlite3.connect(path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM watches").fetchone()[0]
    assert count == 1


def test_legacy_json_store_migrates(monkeypatch, tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({
        "abc123": {
            "watch_id": "abc123",
            "source_url": "https://example.com/story?fbclid=tracker",
            "scope": "web",
            "created_at": "2026-01-01T00:00:00+00:00",
            "last_checked_at": None,
            "last_result_state": None,
            "last_best_match_url": None,
            "active": True,
            "installation_id": "installation-1234",
        }
    }))
    monkeypatch.setenv("FINDREST_WATCH_DB_PATH", str(path))
    loaded = get_watch("abc123")
    assert loaded["source_url"] == "https://example.com/story"
    assert loaded["installation_id"] == "installation-1234"
    assert path.with_suffix(".json.legacy-json").exists()


def test_inactive_history_survives_new_active_watch(monkeypatch, tmp_path):
    path = tmp_path / "watches.sqlite3"
    monkeypatch.setenv("FINDREST_WATCH_DB_PATH", str(path))
    from app.watch_store import deactivate_watch
    first = create_watch("https://example.com/story", "web")
    deactivate_watch(first["watch_id"])
    second = create_watch("https://example.com/story", "web")
    assert first["watch_id"] != second["watch_id"]
    assert [w["watch_id"] for w in list_active()] == [second["watch_id"]]


def test_duplicate_tracking_variants_reuse_same_active_watch(monkeypatch, tmp_path):
    path = tmp_path / "watches.sqlite3"
    monkeypatch.setenv("FINDREST_WATCH_DB_PATH", str(path))
    a = create_watch("https://example.com/story?utm_campaign=a", "web")
    b = create_watch("https://example.com/story?utm_campaign=b", "web")
    assert a["watch_id"] == b["watch_id"]
