import asyncio
from pathlib import Path

from app.candidate_media import fetch_permitted_candidate_media


def test_candidate_gateway_not_configured_does_not_fetch(monkeypatch, tmp_path):
    monkeypatch.delenv("FINDREST_CANDIDATE_MEDIA_ENDPOINT", raising=False)
    result = asyncio.run(fetch_permitted_candidate_media(
        "https://social.example/video/123",
        str(tmp_path),
    ))
    assert result.path is None
    assert result.status == "provider_not_configured"


def test_candidate_gateway_receives_url_and_returns_permitted_media(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_ENDPOINT", "https://gateway.example/fetch")
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_KEY", "secret")

    class Response:
        status_code = 200
        headers = {"content-type": "video/mp4"}
        content = b"permitted-video-bytes"

    calls = []

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    monkeypatch.setattr("app.candidate_media.httpx.AsyncClient", lambda **kwargs: FakeClient())

    result = asyncio.run(fetch_permitted_candidate_media(
        "https://social.example/video/123",
        str(tmp_path),
    ))
    assert result.status == "ok"
    assert Path(result.path).read_bytes() == b"permitted-video-bytes"
    assert calls[0][0] == "https://gateway.example/fetch"
    assert calls[0][1]["json"] == {"candidate_url": "https://social.example/video/123"}
    assert calls[0][1]["headers"]["Authorization"] == "Bearer secret"


def test_candidate_gateway_rejects_non_video_response(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_ENDPOINT", "https://gateway.example/fetch")

    class Response:
        status_code = 200
        headers = {"content-type": "text/html"}
        content = b"<html>login</html>"

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs): return Response()

    monkeypatch.setattr("app.candidate_media.httpx.AsyncClient", lambda **kwargs: FakeClient())
    result = asyncio.run(fetch_permitted_candidate_media("https://example.com/v", str(tmp_path)))
    assert result.path is None
    assert result.status == "unsupported_content_type"
