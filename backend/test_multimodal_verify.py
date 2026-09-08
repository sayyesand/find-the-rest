from app.multimodal_verify import VerificationSignals, fuse_verification


def test_independent_agreement_produces_strong_match():
    r = fuse_verification(VerificationSignals(
        robust_visual=.91,
        audio_fingerprint=.88,
        boundary_visual=.78,
        boundary_audio=.62,
        transcript_semantic=.76,
        scene_semantic=.81,
        has_audio_fingerprint=True,
        has_boundary_audio=True,
        has_transcript=True,
    ))
    assert r.verdict == "strong_match"
    assert r.confidence >= .82
    assert r.agreement_count >= 2


def test_missing_audio_is_not_treated_as_negative_evidence():
    r = fuse_verification(VerificationSignals(
        robust_visual=.90,
        transcript_semantic=.73,
        scene_semantic=.80,
        boundary_visual=.75,
        has_audio_fingerprint=False,
        has_boundary_audio=False,
        has_transcript=True,
    ))
    assert r.verdict in {"strong_match", "likely_match"}
    assert r.confidence > .70


def test_contradictory_channels_suppress_overconfidence():
    r = fuse_verification(VerificationSignals(
        robust_visual=.92,
        audio_fingerprint=.14,
        transcript_semantic=.08,
        scene_semantic=.18,
        boundary_visual=.50,
        has_audio_fingerprint=True,
        has_boundary_audio=False,
        has_transcript=True,
    ))
    assert r.contradiction_penalty > 0
    assert r.verdict != "strong_match"


def test_weak_signals_are_not_verified():
    r = fuse_verification(VerificationSignals(
        robust_visual=.32,
        audio_fingerprint=.28,
        boundary_visual=.25,
        boundary_audio=.10,
        transcript_semantic=.22,
        scene_semantic=.30,
        has_audio_fingerprint=True,
        has_boundary_audio=True,
        has_transcript=True,
    ))
    assert r.verdict == "not_verified"
    assert r.confidence < .46
