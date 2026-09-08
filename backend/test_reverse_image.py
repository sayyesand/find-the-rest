import pytest

from app.models import Candidate
from app.visible_text import VisibleTextEvidence
import app.media_discovery as md


@pytest.mark.asyncio
async def test_reverse_image_can_find_text_free_screenshot(monkeypatch):
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    async def fake_reverse(path):
        return [
            Candidate(
                title="Original wildlife clip",
                url="https://example.com/original",
                platform="web",
                creator="NatureCam",
                reason="reverse-image provider",
                snippet="Longer original upload",
                score=.82,
                evidence={"reverse_image_match": .82},
            )
        ], ["Reverse-image provider returned 1 usable candidate(s)."]

    monkeypatch.setattr(md, "discover_reverse_image", fake_reverse)
    ev = VisibleTextEvidence("", (), (), (), (), 1, "test")
    candidates, notes = await md.discover_from_media("/tmp/fake.jpg", ev)
    assert candidates[0].title == "Original wildlife clip"
    assert candidates[0].evidence["reverse_image_match"] == .82
    assert any("OCR and reverse-image evidence were fused" in n for n in notes)


@pytest.mark.asyncio
async def test_multimodal_duplicate_gets_agreement_boost(monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test")

    async def fake_search(query, source_url, **kwargs):
        return [Candidate(
            title="Maya bridge rescue",
            url="https://example.com/maya",
            platform="web",
            creator="RescueDaily",
            reason="visible text",
            snippet="Maya at the Albuquerque bridge rescue",
            score=.55,
            evidence={"text_similarity": .4},
        )]

    async def fake_reverse(path):
        return [Candidate(
            title="Maya bridge rescue original",
            url="https://example.com/maya",
            platform="web",
            creator="RescueDaily",
            reason="reverse-image provider",
            snippet="same imagery",
            score=.70,
            evidence={"reverse_image_match": .88},
        )], []

    monkeypatch.setattr(md, "search_open_web", fake_search)
    monkeypatch.setattr(md, "discover_reverse_image", fake_reverse)
    ev = VisibleTextEvidence(
        "@RescueDaily Maya Albuquerque bridge rescue",
        ("@RescueDaily",), (), (), ("maya","albuquerque","bridge","rescue"), 1, "test"
    )
    candidates, _ = await md.discover_from_media("/tmp/fake.jpg", ev)
    assert len(candidates) == 1
    assert candidates[0].evidence["multimodal_agreement"] == 1.0
    assert candidates[0].score > .70
