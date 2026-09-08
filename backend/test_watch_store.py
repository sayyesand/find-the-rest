from app.watch_store import create_watch, get_watch, update_watch


def test_create_watch_reuses_active_duplicate(monkeypatch, tmp_path):
    path = tmp_path / "watches.json"
    monkeypatch.setenv("FINDREST_WATCH_PATH", str(path))
    a = create_watch("https://example.com/story", "web")
    b = create_watch("https://example.com/story", "web")
    assert a["watch_id"] == b["watch_id"]
    assert a["active"] is True


def test_watch_can_record_found_state(monkeypatch, tmp_path):
    path = tmp_path / "watches.json"
    monkeypatch.setenv("FINDREST_WATCH_PATH", str(path))
    w = create_watch("https://example.com/story", "web")
    updated = update_watch(
        w["watch_id"],
        last_result_state="continuation_found",
        last_best_match_url="https://example.com/part2",
        active=False,
    )
    assert updated["active"] is False
    loaded = get_watch(w["watch_id"])
    assert loaded["last_result_state"] == "continuation_found"
    assert loaded["last_best_match_url"] == "https://example.com/part2"


def test_deactivate_removes_from_active_list(monkeypatch, tmp_path):
    path = tmp_path / "watches.json"
    monkeypatch.setenv("FINDREST_WATCH_PATH", str(path))
    from app.watch_store import deactivate_watch, list_active
    w = create_watch("https://example.com/another-story", "web")
    assert any(x["watch_id"] == w["watch_id"] for x in list_active())
    deactivate_watch(w["watch_id"])
    assert all(x["watch_id"] != w["watch_id"] for x in list_active())
