import pytest

from app.models import AnalyzeRequest, Candidate
import app.service as service


@pytest.mark.asyncio
async def test_social_caption_seeds_youtube_continuation_search(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")

    async def fake_public_metadata(_url):
        return {"title": "", "description": "", "creator": None}

    async def fake_search(query, **_kwargs):
        assert "maya bridge rescue" in query
        return [Candidate(
            title="Maya Bridge Rescue (Part 2)",
            url="https://youtube.com/watch?v=part2",
            platform="youtube",
            creator="Rescue Stories",
            reason="Explicit continuation wording.",
            score=.62,
            evidence={"text_similarity": .55, "continuation_signal": 1.0},
        )]

    monkeypatch.setattr(service, "public_metadata", fake_public_metadata)
    monkeypatch.setattr(service, "search_candidates", fake_search)

    result = await service.analyze(
        AnalyzeRequest(
            url="https://www.instagram.com/reel/example",
            scope="web",
            intent="continue_story",
        ),
        source_visible_text="Maya bridge rescue Part 1",
    )

    assert result.best_match is not None
    assert "Part 2" in result.best_match.title
    assert result.result_state == "continuation_found"
