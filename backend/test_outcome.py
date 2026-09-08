from app.models import Candidate
from app.outcome import classify_outcome


def c(score=.6):
    return Candidate(
        title="Story Part 2",
        url="https://example.com/p2",
        platform="web",
        reason="test",
        score=score,
        evidence={},
    )


def test_continuation_found_state():
    out = classify_outcome(
        match_type="official_continuation",
        best=c(.72),
        candidates=[c(.72)],
        source_text="Story Part 1",
        cliffhanger_strength=.8,
        broad_search_available=True,
    )
    assert out.state == "continuation_found"
    assert "watch_continuation" in out.actions


def test_full_original_state():
    out = classify_outcome(
        match_type="full_original",
        best=c(.78),
        candidates=[c(.78)],
        source_text="short excerpt",
        cliffhanger_strength=0,
        broad_search_available=True,
    )
    assert out.state == "full_original_found"


def test_related_only_does_not_claim_continuation():
    out = classify_outcome(
        match_type="no_match",
        best=None,
        candidates=[c(.33)],
        source_text="Maya bridge rescue",
        cliffhanger_strength=.2,
        broad_search_available=True,
    )
    assert out.state == "related_only"
    assert "not enough evidence" in out.message.lower()


def test_likely_not_posted_yet_requires_broad_search():
    out = classify_outcome(
        match_type="no_match",
        best=None,
        candidates=[],
        source_text="Story Part 1 — follow for Part 2",
        cliffhanger_strength=.8,
        broad_search_available=True,
    )
    assert out.state == "likely_not_posted_yet"
    assert out.confidence <= .68

    no_provider = classify_outcome(
        match_type="no_match",
        best=None,
        candidates=[],
        source_text="Story Part 1 — follow for Part 2",
        cliffhanger_strength=.8,
        broad_search_available=False,
    )
    assert no_provider.state != "likely_not_posted_yet"


def test_empty_context_is_insufficient_context():
    out = classify_outcome(
        match_type="no_match",
        best=None,
        candidates=[],
        source_text="",
        cliffhanger_strength=0,
        broad_search_available=True,
    )
    assert out.state == "insufficient_context"
