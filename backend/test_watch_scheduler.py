from datetime import datetime, timezone, timedelta

from app.watch_store import create_watch, update_watch, list_due


def test_new_active_watch_is_due(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_WATCH_PATH", str(tmp_path / "w.json"))
    w = create_watch("https://example.com/story", "web")
    due = list_due(interval_minutes=360, limit=10)
    assert [x["watch_id"] for x in due] == [w["watch_id"]]


def test_recently_checked_watch_is_not_due(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_WATCH_PATH", str(tmp_path / "w.json"))
    w = create_watch("https://example.com/story", "web")
    update_watch(w["watch_id"], last_checked_at=datetime.now(timezone.utc).isoformat())
    assert list_due(interval_minutes=360, limit=10) == []


def test_old_watch_is_due_and_inactive_is_not(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_WATCH_PATH", str(tmp_path / "w.json"))
    old = create_watch("https://example.com/old", "web")
    inactive = create_watch("https://example.com/inactive", "web")
    past = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
    update_watch(old["watch_id"], last_checked_at=past)
    update_watch(inactive["watch_id"], last_checked_at=past, active=False)
    ids = {x["watch_id"] for x in list_due(interval_minutes=360, limit=10)}
    assert old["watch_id"] in ids
    assert inactive["watch_id"] not in ids


def test_due_list_obeys_batch_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_WATCH_PATH", str(tmp_path / "w.json"))
    for i in range(5):
        create_watch(f"https://example.com/{i}", "web")
    assert len(list_due(interval_minutes=360, limit=2)) == 2
