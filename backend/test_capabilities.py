import pytest
from app.main import capabilities

@pytest.mark.asyncio
async def test_capabilities_reflect_configuration(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave")
    monkeypatch.delenv("FINDREST_REVERSE_IMAGE_ENDPOINT", raising=False)
    monkeypatch.setenv("ENABLE_LOCAL_TRANSCRIPTION", "0")
    c = await capabilities()
    assert c.youtube_search is True
    assert c.open_web_search is True
    assert c.reverse_image_search is False
    assert c.local_transcription is False
    assert c.watch_store is True
    assert c.feedback_store is True
