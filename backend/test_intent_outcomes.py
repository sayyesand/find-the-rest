from app.models import Candidate
from app.outcome import classify_outcome, is_success_state


def candidate(
    score=.72,
    *,
    trace_role=None,
    trace_score=0.0,
    evidence=None,
):
    return Candidate(
        title="Fixture",
        url="https://example.com/item",
        platform="web",
        reason="fixture",
        score=score,
        trace_role=trace_role,
        trace_score=trace_score,
        evidence=evidence or {},
    )


def test_original_source_intent_has_dedicated_success_state():
    c = candidate(
        trace_role="likely_original",
        trace_score=.62,
        evidence={
            "intent_fit": .66,
            "trace_earlier_upload": .8,
            "trace_creator_authority": .7,
        },
    )
    out = classify_outcome(
        match_type="no_match",
        best=c,
        candidates=[c],
        source_text="reposted clip",
        cliffhanger_strength=0,
        broad_search_available=True,
        intent="original_source",
    )
    assert out.state == "original_source_found"
    assert "original source" in out.message.lower()
    assert is_success_state(out.state)


def test_original_source_intent_does_not_mislabel_generic_match():
    c = candidate(evidence={"intent_fit": .10})
    out = classify_outcome(
        match_type="official_continuation",
        best=c,
        candidates=[c],
        source_text="some story",
        cliffhanger_strength=.8,
        broad_search_available=True,
        intent="original_source",
    )
    assert out.state == "related_only"
    assert "provenance" in out.message.lower()
    assert "continuation" not in out.message.lower()


def test_other_copies_intent_has_copy_success_state():
    c = candidate(
        trace_role="likely_repost",
        evidence={"intent_fit": .9, "reverse_image_match": .82},
    )
    out = classify_outcome(
        match_type="no_match",
        best=c,
        candidates=[c],
        source_text="clip",
        cliffhanger_strength=0,
        broad_search_available=True,
        intent="other_copies",
    )
    assert out.state == "copies_found"
    assert "copy" in out.message.lower() or "repost" in out.message.lower()


def test_identify_intent_has_context_match_state():
    c = candidate(evidence={"intent_fit": .71, "visible_text_match": .64})
    out = classify_outcome(
        match_type="no_match",
        best=c,
        candidates=[c],
        source_text="visible sign and machine",
        cliffhanger_strength=0,
        broad_search_available=True,
        intent="identify_shown",
    )
    assert out.state == "identification_found"
    assert "context" in out.message.lower()


def test_not_posted_hint_only_applies_to_continue_story():
    args = dict(
        match_type="no_match",
        best=None,
        candidates=[],
        source_text="Part 1 follow for Part 2",
        cliffhanger_strength=.9,
        broad_search_available=True,
    )
    continue_out = classify_outcome(**args, intent="continue_story")
    source_out = classify_outcome(**args, intent="original_source")
    assert continue_out.state == "likely_not_posted_yet"
    assert source_out.state == "no_verified_source"


def test_goal_specific_no_match_states():
    cases = {
        "full_original": "no_verified_full_original",
        "original_source": "no_verified_source",
        "other_copies": "no_verified_copy",
        "identify_shown": "no_verified_identification",
    }
    for intent, expected in cases.items():
        out = classify_outcome(
            match_type="no_match",
            best=None,
            candidates=[],
            source_text="usable context",
            cliffhanger_strength=0,
            broad_search_available=True,
            intent=intent,
        )
        assert out.state == expected
