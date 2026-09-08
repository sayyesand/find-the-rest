from app.models import Candidate
from app.source_trace import trace_candidate, trace_and_promote
from app.adapters.youtube import iso8601_duration_seconds

def c(title, score=.6, duration=None, published=None, creator=None, reason="", textsim=.5):
    return Candidate(
        title=title,
        url="https://youtube.com/watch?v=" + title.replace(" ", "_"),
        platform="youtube",
        creator=creator,
        published_at=published,
        reason=reason,
        score=score,
        evidence={"text_similarity": textsim},
        duration_seconds=duration,
    )

def test_iso_duration():
    assert iso8601_duration_seconds("PT1M30S") == 90
    assert iso8601_duration_seconds("PT2H3M4S") == 7384
    assert iso8601_duration_seconds("P1DT1H") == 90000

def test_longer_related_video_can_be_likely_original():
    item = c("Dog rescue complete story", duration=360, reason="full original source", textsim=.55)
    traced = trace_candidate(
        item, source_creator="reposter", source_duration=60, source_published="2026-01-10T00:00:00Z"
    )
    assert traced.trace_role == "likely_original"
    assert traced.trace_score >= .5
    assert traced.evidence["trace_duration_advantage"] == 1.0

def test_fragment_is_penalized():
    item = c("Dog rescue Part 1 clip", duration=45, reason="short clip")
    traced = trace_candidate(
        item, source_creator=None, source_duration=60, source_published=None
    )
    assert traced.trace_role == "fragment"
    assert traced.evidence["trace_fragment_penalty"] == 1.0

def test_originality_breaks_close_contest_not_weak_match():
    original = c("Full original complete story", score=.58, duration=400, reason="full original", textsim=.55)
    repost = c("Dog rescue continuation", score=.62, duration=60, reason="continued", textsim=.55)
    ranked = trace_and_promote(
        [repost, original], source_creator="clipper", source_duration=60, source_published=None
    )
    assert ranked[0].trace_role == "likely_original"

    weak_original = c("Full original unrelated", score=.20, duration=400, reason="full original", textsim=.05)
    ranked2 = trace_and_promote(
        [repost, weak_original], source_creator="clipper", source_duration=60, source_published=None
    )
    assert ranked2[0].title == "Dog rescue continuation"

def test_earlier_upload_adds_trace_evidence():
    item = c("Dog rescue full video", duration=180, published="2025-12-01T00:00:00Z", reason="full video")
    traced = trace_candidate(
        item, source_creator=None, source_duration=60, source_published="2026-01-15T00:00:00Z"
    )
    assert traced.evidence["trace_earlier_upload"] == 1.0
