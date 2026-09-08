import pytest

from app.models import Candidate
from app.visible_text import VisibleTextEvidence
import app.media_discovery as md


@pytest.mark.asyncio
async def test_no_distinctive_visible_text_returns_no_candidates(monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test")
    ev = VisibleTextEvidence("", (), (), (), (), 1, "test")
    candidates, notes = await md.discover_from_visible_text(ev)
    assert candidates == []
    assert any("No sufficiently distinctive" in n for n in notes)


@pytest.mark.asyncio
async def test_visible_text_discovery_ranks_matching_candidate(monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test")

    async def fake_search(query, source_url, **kwargs):
        return [
            Candidate(
                title="Maya bridge rescue update",
                url="https://example.com/maya",
                platform="web",
                creator="RescueDaily",
                reason=kwargs.get("reason_label", "test"),
                snippet="Maya returned to the Albuquerque bridge after the Route 66 rescue.",
                score=.42,
                evidence={"text_similarity": .35},
            ),
            Candidate(
                title="Tomato soup recipe",
                url="https://example.com/soup",
                platform="web",
                reason=kwargs.get("reason_label", "test"),
                snippet="A simple tomato soup recipe.",
                score=.15,
                evidence={"text_similarity": .1},
            ),
        ]

    monkeypatch.setattr(md, "search_open_web", fake_search)
    ev = VisibleTextEvidence(
        "@RescueDaily Maya returned to the Albuquerque bridge after the Route 66 rescue",
        ("@RescueDaily",),
        (),
        (),
        ("maya","albuquerque","bridge","route","rescue"),
        1,
        "test",
    )
    candidates, notes = await md.discover_from_visible_text(ev)
    assert candidates
    assert candidates[0].title == "Maya bridge rescue update"
    assert candidates[0].evidence["visible_text_match"] > 0
    assert any("Standalone screenshot discovery searched" in n for n in notes)


@pytest.mark.asyncio
async def test_discovery_requires_search_provider(monkeypatch):
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    ev = VisibleTextEvidence(
        "Maya Albuquerque bridge rescue",
        (),
        (),
        (),
        ("maya","albuquerque","bridge","rescue"),
        1,
        "test",
    )
    candidates, notes = await md.discover_from_visible_text(ev)
    assert candidates == []
    assert any("BRAVE_SEARCH_API_KEY" in n for n in notes)
