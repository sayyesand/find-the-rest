import asyncio

from app.push import register_device, get_device, token_fingerprint, send_found_notification


def test_push_registration_hides_raw_token(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_PUSH_STORE_PATH", str(tmp_path / "push.json"))
    token = "a" * 64
    public = register_device("installation-1234", token, "sandbox")
    assert public["token_fingerprint"] == token_fingerprint(token)
    assert "device_token" not in public
    stored = get_device("installation-1234")
    assert stored["device_token"] == token


def test_push_is_not_sent_without_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_PUSH_STORE_PATH", str(tmp_path / "push.json"))
    monkeypatch.delenv("FINDREST_PUSH_ENDPOINT", raising=False)
    register_device("installation-1234", "b" * 64, "sandbox")
    sent, status = asyncio.run(send_found_notification(
        installation_id="installation-1234",
        watch_id="watch1",
        result_state="continuation_found",
        best_match_url="https://example.com/part2",
    ))
    assert sent is False
    assert status == "push_provider_not_configured"


def test_duplicate_event_is_suppressed_after_success(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_PUSH_STORE_PATH", str(tmp_path / "push.json"))
    monkeypatch.setenv("FINDREST_PUSH_ENDPOINT", "https://push.example/send")
    register_device("installation-1234", "c" * 64, "production")

    class Response:
        status_code = 200

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs): return Response()

    monkeypatch.setattr("app.push.httpx.AsyncClient", lambda **kwargs: FakeClient())

    async def run():
        first = await send_found_notification(
            installation_id="installation-1234",
            watch_id="watch1",
            result_state="continuation_found",
            best_match_url="https://example.com/part2",
        )
        second = await send_found_notification(
            installation_id="installation-1234",
            watch_id="watch1",
            result_state="continuation_found",
            best_match_url="https://example.com/part2",
        )
        return first, second

    first, second = asyncio.run(run())
    assert first == (True, "sent")
    assert second == (False, "duplicate_suppressed")
