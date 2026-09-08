import pytest

from app.service import _hunt_cross_platform
from app.outcome import classify_outcome


@pytest.mark.asyncio
async def test_search_coverage_counts_completed_and_failed_queries(monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "configured")
    calls = {"n": 0}

    async def fake_search(query, source_url, **kwargs):
        calls["n"] += 1
        if calls["n"] in {2, 5}:
            raise RuntimeError("provider failure")
        return []

    monkeypatch.setattr("app.service.search_open_web", fake_search)

    results, coverage = await _hunt_cross_platform(
        source_url="https://example.com/source",
        source_platform="tiktok",
        source_title="Lost dog story",
        source_description="A dog named Pepper disappeared after a storm",
        source_creator="Maya",
        scope="web",
        fingerprint_queries=["pepper storm dog", "maya pepper"],
        ending_queries=["pepper storm continued"],
        intent="continue_story",
    )

    assert results == []
    assert coverage["attempted"] >= 5
    assert coverage["completed"] == coverage["attempted"] - 2
    assert coverage["failed"] == 2
    assert coverage["coverage_ratio"] == pytest.approx(coverage["completed"] / coverage["attempted"], abs=.0001)


@pytest.mark.asyncio
async def test_unconfigured_provider_has_zero_coverage(monkeypatch):
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    _, coverage = await _hunt_cross_platform(
        source_url="https://example.com/source",
        source_platform="web",
        source_title="Story Part 1",
        source_description="follow for part 2",
        source_creator=None,
        scope="web",
    )
    assert coverage["provider_configured"] is False
    assert coverage["attempted"] == 0
    assert coverage["completed"] == 0


def test_likely_not_posted_requires_actual_broad_search_completion():
    weak_coverage = classify_outcome(
        match_type="no_match",
        best=None,
        candidates=[],
        source_text="Part 1 — follow for Part 2",
        cliffhanger_strength=.9,
        broad_search_available=False,
    )
    enough_coverage = classify_outcome(
        match_type="no_match",
        best=None,
        candidates=[],
        source_text="Part 1 — follow for Part 2",
        cliffhanger_strength=.9,
        broad_search_available=True,
    )
    assert weak_coverage.state == "no_verified_match"
    assert enough_coverage.state == "likely_not_posted_yet"


def test_ios_displays_search_coverage_and_nonpublication_guard():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    models = (root / "ios/FindTheRest/APIModels.swift").read_text()
    content = (root / "ios/FindTheRest/ContentView.swift").read_text()
    assert "struct SearchCoverage" in models
    assert "broadEnoughForNonpublicationHint" in models
    assert "Search coverage:" in content
    assert "will not imply that the missing continuation has not been posted" in content
