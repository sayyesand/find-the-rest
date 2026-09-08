import asyncio
from pathlib import Path

from app.candidate_media import configured, fetch_permitted_candidate_media


def test_candidate_media_gateway_requires_https(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_ENDPOINT", "http://gateway.example/fetch")
    monkeypatch.delenv("FINDREST_CANDIDATE_MEDIA_ALLOWED_HOSTS", raising=False)
    assert configured() is False
    result = asyncio.run(fetch_permitted_candidate_media("https://example.com/video", str(tmp_path)))
    assert result.path is None
    assert "https_required" in result.status


def test_candidate_media_gateway_host_allowlist(monkeypatch):
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_ALLOWED_HOSTS", "trusted.example")
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_ENDPOINT", "https://evil.example/fetch")
    assert configured() is False
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_ENDPOINT", "https://trusted.example/fetch")
    assert configured() is True


def test_candidate_media_rejects_local_and_private_candidate_urls(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_ENDPOINT", "https://trusted.example/fetch")
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_ALLOWED_HOSTS", "trusted.example")
    for url in (
        "http://localhost/video",
        "http://127.0.0.1/video",
        "http://10.0.0.5/video",
        "http://169.254.169.254/latest/meta-data",
        "file:///etc/passwd",
    ):
        result = asyncio.run(fetch_permitted_candidate_media(url, str(tmp_path)))
        assert result.path is None
        assert result.status == "invalid_candidate_url"


def test_candidate_media_rejects_redirect(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_ENDPOINT", "https://trusted.example/fetch")
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_ALLOWED_HOSTS", "trusted.example")

    class Resp:
        status_code = 302
        headers = {"location": "https://evil.example/steal"}
        content = b""

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs): return Resp()

    monkeypatch.setattr("app.candidate_media.httpx.AsyncClient", lambda **kwargs: Client())
    result = asyncio.run(fetch_permitted_candidate_media("https://example.com/video", str(tmp_path)))
    assert result.path is None
    assert result.status == "provider_redirect_rejected"


def test_candidate_media_rejects_oversize_from_content_length(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_ENDPOINT", "https://trusted.example/fetch")
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_ALLOWED_HOSTS", "trusted.example")
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_MAX_BYTES", "1000000")

    class Resp:
        status_code = 200
        headers = {"content-type": "video/mp4", "content-length": "2000000"}
        content = b"x"

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs): return Resp()

    monkeypatch.setattr("app.candidate_media.httpx.AsyncClient", lambda **kwargs: Client())
    result = asyncio.run(fetch_permitted_candidate_media("https://example.com/video", str(tmp_path)))
    assert result.path is None
    assert result.status == "media_too_large"


def test_candidate_media_does_not_follow_redirects_and_sends_auth_only_to_configured_host(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_ENDPOINT", "https://trusted.example/fetch")
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_ALLOWED_HOSTS", "trusted.example")
    monkeypatch.setenv("FINDREST_CANDIDATE_MEDIA_KEY", "secret")
    seen = {}

    class Resp:
        status_code = 200
        headers = {"content-type": "video/mp4"}
        content = b"abc"

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, url, **kwargs):
            seen["url"] = url
            seen["headers"] = kwargs["headers"]
            return Resp()

    def factory(**kwargs):
        seen["follow_redirects"] = kwargs["follow_redirects"]
        return Client()

    monkeypatch.setattr("app.candidate_media.httpx.AsyncClient", factory)
    result = asyncio.run(fetch_permitted_candidate_media("https://example.com/video", str(tmp_path)))
    assert result.status == "ok"
    assert seen["url"] == "https://trusted.example/fetch"
    assert seen["headers"]["Authorization"] == "Bearer secret"
    assert seen["follow_redirects"] is False
