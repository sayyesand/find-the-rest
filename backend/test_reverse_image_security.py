import json
import asyncio
from pathlib import Path

from app.reverse_image import configured, discover_reverse_image


def test_reverse_image_requires_https(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_REVERSE_IMAGE_ENDPOINT", "http://gateway.example/search")
    monkeypatch.delenv("FINDREST_REVERSE_IMAGE_ALLOWED_HOSTS", raising=False)
    assert configured() is False
    media = tmp_path / "x.png"
    media.write_bytes(b"x")
    results, notes = asyncio.run(discover_reverse_image(str(media)))
    assert results == []
    assert any("https_required" in n for n in notes)


def test_reverse_image_host_allowlist(monkeypatch):
    monkeypatch.setenv("FINDREST_REVERSE_IMAGE_ENDPOINT", "https://evil.example/search")
    monkeypatch.setenv("FINDREST_REVERSE_IMAGE_ALLOWED_HOSTS", "trusted.example")
    assert configured() is False
    monkeypatch.setenv("FINDREST_REVERSE_IMAGE_ENDPOINT", "https://trusted.example/search")
    assert configured() is True


def test_reverse_image_rejects_redirect_and_wrong_content_type(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_REVERSE_IMAGE_ENDPOINT", "https://trusted.example/search")
    monkeypatch.setenv("FINDREST_REVERSE_IMAGE_ALLOWED_HOSTS", "trusted.example")
    media = tmp_path / "x.png"
    media.write_bytes(b"x")

    class Resp:
        def __init__(self, status, content_type="application/json", content=b"{}"):
            self.status_code=status
            self.headers={"content-type":content_type}
            self.content=content
        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError("bad")
        def json(self):
            import json
            return json.loads(self.content.decode())

    class Client:
        def __init__(self, response): self.response=response
        async def __aenter__(self): return self
        async def __aexit__(self,*a): return False
        async def post(self,*a,**k): return self.response

    monkeypatch.setattr("app.reverse_image.httpx.AsyncClient", lambda **k: Client(Resp(302)))
    results, notes = asyncio.run(discover_reverse_image(str(media)))
    assert results == []
    assert any("redirect" in n.lower() for n in notes)

    monkeypatch.setattr("app.reverse_image.httpx.AsyncClient", lambda **k: Client(Resp(200, "text/html", b"<html/>")))
    results, notes = asyncio.run(discover_reverse_image(str(media)))
    assert results == []
    assert any("content type" in n.lower() for n in notes)


def test_reverse_image_response_size_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_REVERSE_IMAGE_ENDPOINT", "https://trusted.example/search")
    monkeypatch.setenv("FINDREST_REVERSE_IMAGE_ALLOWED_HOSTS", "trusted.example")
    monkeypatch.setenv("FINDREST_REVERSE_IMAGE_MAX_RESPONSE_BYTES", "65536")
    media = tmp_path / "x.png"
    media.write_bytes(b"x")

    class Resp:
        status_code=200
        headers={"content-type":"application/json"}
        content=b"x"*70000
        def raise_for_status(self): pass
        def json(self): return {}
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self,*a): return False
        async def post(self,*a,**k): return Resp()

    monkeypatch.setattr("app.reverse_image.httpx.AsyncClient", lambda **k: Client())
    results, notes = asyncio.run(discover_reverse_image(str(media)))
    assert results == []
    assert any("size limit" in n.lower() for n in notes)


def test_reverse_image_canonical_dedupe(monkeypatch, tmp_path):
    monkeypatch.setenv("FINDREST_REVERSE_IMAGE_ENDPOINT", "https://trusted.example/search")
    monkeypatch.setenv("FINDREST_REVERSE_IMAGE_ALLOWED_HOSTS", "trusted.example")
    media = tmp_path / "x.png"
    media.write_bytes(b"x")

    payload = {
        "results": [
            {"url":"https://example.com/watch?v=7&utm_source=a","title":"Clip A","score":0.61},
            {"url":"https://www.example.com/watch?utm_campaign=b&v=7","title":"Clip B","score":0.83},
        ]
    }

    class Resp:
        status_code=200
        headers={"content-type":"application/json"}
        content=json.dumps(payload).encode()
        def raise_for_status(self): pass
        def json(self): return payload
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self,*a): return False
        async def post(self,*a,**k): return Resp()

    monkeypatch.setattr("app.reverse_image.httpx.AsyncClient", lambda **k: Client())
    results, _ = asyncio.run(discover_reverse_image(str(media)))
    assert len(results) == 1
    assert results[0].title == "Clip B"
    assert results[0].score == 0.83
