from app.hunter import build_search_plans
from app.intent import rank_for_intent
from app.models import Candidate


def _candidate(title, url, score, *, role=None, trace_score=0.0, evidence=None):
    return Candidate(
        title=title,
        url=url,
        platform="web",
        creator="Creator",
        reason="fixture",
        score=score,
        trace_role=role,
        trace_score=trace_score,
        evidence=evidence or {},
    )


def test_full_original_intent_changes_query_priority():
    plans = build_search_plans(
        source_platform="tiktok",
        title="Rescued owl story",
        description="Maya takes an owl to a wildlife center",
        creator="Maya",
        scope="web",
        intent="full_original",
    )
    assert plans[0].label == "full original"
    assert plans[1].label == "original source"


def test_original_source_intent_prioritizes_close_provenance_match():
    continuation = _candidate(
        "Story Part 2", "https://example.com/p2", .73,
        evidence={"continuation_signal": 1.0},
    )
    original = _candidate(
        "Original source full clip", "https://example.com/original", .70,
        role="likely_original", trace_score=.9,
        evidence={"trace_earlier_upload": 1.0, "trace_creator_authority": .65},
    )
    ranked = rank_for_intent([continuation, original], "original_source")
    assert ranked[0].url == original.url
    assert ranked[0].evidence["intent_fit"] > 0


def test_intent_cannot_rescue_materially_weak_candidate():
    strong = _candidate("Strong topical match", "https://example.com/strong", .82)
    weak_original = _candidate(
        "Original source", "https://example.com/weak", .40,
        role="likely_original", trace_score=1.0,
        evidence={"trace_earlier_upload": 1.0},
    )
    ranked = rank_for_intent([strong, weak_original], "original_source")
    assert ranked[0].url == strong.url


def test_identify_intent_uses_visual_and_story_clues():
    c = _candidate(
        "Unknown scene", "https://example.com/id", .55,
        evidence={"reverse_image_match": .88, "story_fingerprint": .4},
    )
    ranked = rank_for_intent([c], "identify_shown")
    assert ranked[0].evidence["intent_fit"] == .88
