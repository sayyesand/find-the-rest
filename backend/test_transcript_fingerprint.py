import pytest
from app.models import AnalyzeRequest, Candidate
import app.service as service

@pytest.mark.asyncio
async def test_transcript_drives_search_when_page_metadata_is_empty(monkeypatch):
    async def fake_meta(url):
        return {"url": url, "platform": "instagram"}

    captured = {}
    async def fake_hunt(**kwargs):
        captured.update(kwargs)
        return [Candidate(
            title="Maya returns to Route 66 bridge with the rescued dog",
            url="https://example.com/result",
            platform="web",
            creator="RescueDaily",
            reason="story fingerprint search: Maya returned to the Route 66 bridge after hearing barking",
            score=0.40,
            evidence={"text_similarity": 0.10},
        )]

    monkeypatch.setattr(service, "public_metadata", fake_meta)
    monkeypatch.setattr(service, "_hunt_cross_platform", fake_hunt)
    transcript = "Maya heard barking under the old Route 66 bridge and climbed down to rescue a dog."
    result = await service.analyze(
        AnalyzeRequest(url="https://www.instagram.com/reel/example", scope="web"),
        source_transcript=transcript,
    )
    assert captured["source_transcript"] == transcript
    assert captured["fingerprint_queries"]
    assert any("Story fingerprint includes spoken words" in note for note in result.notes)
    assert result.candidates
    assert result.candidates[0].evidence["story_fingerprint"] > 0

def test_transcription_switch_accepts_deployment_env(monkeypatch):
    import app.semantic as semantic
    monkeypatch.delenv("FINDREST_LOCAL_WHISPER", raising=False)
    monkeypatch.setenv("ENABLE_LOCAL_TRANSCRIPTION", "0")
    text, backend = semantic.transcribe_media("/does/not/matter.mp4")
    assert text is None
    assert backend == "not_enabled"
