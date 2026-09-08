from app.models import Candidate, MultimodalVerifyResponse
from app.verification_rank import fuse_candidate_verification, rerank_verified_candidates


def candidate(url, score):
    return Candidate(
        title=url.rsplit("/", 1)[-1],
        url=url,
        platform="web",
        reason="fixture",
        score=score,
    )


def verification(verdict, confidence, contradiction=0.0):
    return MultimodalVerifyResponse(
        verdict=verdict,
        confidence=confidence,
        agreement_count=2 if verdict in {"strong_match", "likely_match"} else 0,
        contradiction_penalty=contradiction,
        robust_visual_similarity=.8 if verdict != "not_verified" else .2,
        audio_fingerprint_similarity=.7 if verdict != "not_verified" else .1,
        boundary_visual_continuity=.6,
        boundary_audio_continuity=.5,
        transcript_semantic=.7 if verdict != "not_verified" else .1,
        scene_semantic=.7 if verdict != "not_verified" else .2,
        contributions={},
        transcript_backend="fixture",
        notes=[],
    )


def test_strong_verification_promotes_but_is_bounded():
    c = candidate("https://example.com/a", .70)
    result = fuse_candidate_verification(c, verification("strong_match", .90))
    assert result.disposition == "promote"
    assert .80 <= result.adjusted_score <= .84
    assert result.adjusted_score < .90


def test_not_verified_demotes_but_does_not_erase_candidate():
    c = candidate("https://example.com/a", .78)
    result = fuse_candidate_verification(c, verification("not_verified", .30, contradiction=.18))
    assert result.disposition == "demote"
    assert .55 <= result.adjusted_score < .78


def test_unavailable_provider_leaves_search_score_unchanged():
    c = candidate("https://example.com/a", .66)
    result = fuse_candidate_verification(c, None, provider_status="candidate_unavailable")
    assert result.disposition == "unverified"
    assert result.adjusted_score == .66
    assert result.delta == 0


def test_second_candidate_can_overtake_failed_top_candidate():
    first = candidate("https://example.com/first", .79)
    second = candidate("https://example.com/second", .73)
    ranked = rerank_verified_candidates([
        (first, verification("not_verified", .28, contradiction=.15), "ok"),
        (second, verification("strong_match", .91), "ok"),
    ])
    assert str(ranked[0].candidate.url).startswith("https://example.com/second")
    assert ranked[0].disposition == "promote"


def test_possible_match_does_not_overpower_large_search_gap():
    first = candidate("https://example.com/first", .82)
    second = candidate("https://example.com/second", .60)
    ranked = rerank_verified_candidates([
        (first, verification("possible_match", .55), "ok"),
        (second, verification("likely_match", .70), "ok"),
    ])
    assert str(ranked[0].candidate.url).startswith("https://example.com/first")
