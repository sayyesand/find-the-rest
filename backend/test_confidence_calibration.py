from app.confidence import confidence_profile, annotate_confidence
from app.models import Candidate


def c(score=.8, evidence=None, trace_role=None, trace_score=0.0):
    return Candidate(
        title="fixture",
        url="https://example.com/x",
        platform="web",
        reason="fixture",
        score=score,
        evidence=evidence or {},
        trace_role=trace_role,
        trace_score=trace_score,
    )


def test_single_metadata_family_cannot_be_high_confidence():
    p = confidence_profile(c(.82, {"text_similarity": .9, "story_fingerprint": .92, "ending_continuity": .88}))
    assert p.family_count == 1
    assert p.calibrated <= .42
    assert p.grade == "low"


def test_multiple_independent_metadata_families_can_clear_tentative_threshold():
    p = confidence_profile(c(.66, {
        "story_fingerprint": .72,
        "continuation_signal": 1.0,
        "creator_match": 1.0,
        "sequence_signal": .65,
    }))
    assert p.family_count >= 4
    assert p.strong_family_count >= 4
    assert p.calibrated == .66
    assert p.grade == "moderate"


def test_direct_media_plus_independent_support_can_be_high():
    p = confidence_profile(c(.88, {
        "story_fingerprint": .70,
        "creator_match": 1.0,
        "reverse_image_match": .91,
        "transcript_semantic": .77,
    }))
    assert p.metadata_only is False
    assert p.calibrated == .88
    assert p.grade == "high"


def test_many_weak_signals_do_not_become_strong():
    p = confidence_profile(c(.75, {
        "story_fingerprint": .30,
        "continuation_signal": .28,
        "creator_match": .25,
        "sequence_signal": .22,
        "trace_earlier_upload": .20,
    }))
    assert p.strong_family_count == 0
    assert p.calibrated <= .48


def test_large_contradiction_caps_confidence():
    p = confidence_profile(c(.90, {
        "story_fingerprint": .8,
        "continuation_signal": 1.0,
        "creator_match": 1.0,
        "sequence_signal": .7,
        "contradiction_penalty": .30,
    }))
    assert p.calibrated <= .54


def test_annotation_exposes_calibration_without_overwriting_raw_score():
    candidate = c(.72, {"story_fingerprint": .7, "creator_match": 1.0, "continuation_signal": 1.0})
    updated = annotate_confidence(candidate)
    assert updated.score == .72
    assert "calibrated_confidence" in updated.evidence
    assert "evidence_family_count" in updated.evidence
