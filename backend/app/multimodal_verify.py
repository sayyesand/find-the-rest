from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationSignals:
    robust_visual: float = 0.0
    audio_fingerprint: float = 0.0
    boundary_visual: float = 0.0
    boundary_audio: float = 0.0
    transcript_semantic: float = 0.0
    scene_semantic: float = 0.0
    appearance_similarity: float = 0.0
    has_appearance: bool = False
    has_audio_fingerprint: bool = False
    has_boundary_audio: bool = False
    has_transcript: bool = False


@dataclass(frozen=True)
class VerificationResult:
    confidence: float
    verdict: str
    agreement_count: int
    contradiction_penalty: float
    contributions: dict[str, float]


WEIGHTS = {
    "robust_visual": .26,
    "audio_fingerprint": .22,
    "boundary_visual": .12,
    "boundary_audio": .08,
    "transcript_semantic": .20,
    "scene_semantic": .10,
    "appearance_similarity": .12,
}


def fuse_verification(signals: VerificationSignals) -> VerificationResult:
    values = {
        "robust_visual": max(0.0, min(1.0, signals.robust_visual)),
        "audio_fingerprint": max(0.0, min(1.0, signals.audio_fingerprint)),
        "boundary_visual": max(0.0, min(1.0, signals.boundary_visual)),
        "boundary_audio": max(0.0, min(1.0, signals.boundary_audio)),
        "transcript_semantic": max(0.0, min(1.0, signals.transcript_semantic)),
        "scene_semantic": max(0.0, min(1.0, signals.scene_semantic)),
        "appearance_similarity": max(0.0, min(1.0, signals.appearance_similarity)),
    }
    available = {
        "robust_visual": True,
        "audio_fingerprint": signals.has_audio_fingerprint,
        "boundary_visual": True,
        "boundary_audio": signals.has_boundary_audio,
        "transcript_semantic": signals.has_transcript,
        "scene_semantic": True,
        "appearance_similarity": signals.has_appearance,
    }

    denom = sum(WEIGHTS[k] for k, ok in available.items() if ok)
    weighted = sum(values[k] * WEIGHTS[k] for k, ok in available.items() if ok) / max(denom, 1e-9)

    # Independent strong channels agreeing should raise confidence slightly.
    strong = [
        values["robust_visual"] >= .76,
        signals.has_audio_fingerprint and values["audio_fingerprint"] >= .72,
        signals.has_transcript and values["transcript_semantic"] >= .62,
        values["scene_semantic"] >= .68,
        signals.has_appearance and values["appearance_similarity"] >= .70,
        values["boundary_visual"] >= .72,
    ]
    agreement_count = sum(bool(x) for x in strong)
    agreement_boost = min(.10, max(0, agreement_count - 1) * .025)

    # Strong disagreement matters: one high-confidence identity channel plus another
    # available channel that strongly rejects the match should suppress overconfidence.
    contradiction_penalty = 0.0
    identity_high = values["robust_visual"] >= .82 or (
        signals.has_audio_fingerprint and values["audio_fingerprint"] >= .82
    )
    if identity_high:
        lows = 0
        if signals.has_audio_fingerprint and values["audio_fingerprint"] < .30:
            lows += 1
        if signals.has_transcript and values["transcript_semantic"] < .18:
            lows += 1
        if values["scene_semantic"] < .22:
            lows += 1
        if signals.has_appearance and values["appearance_similarity"] < .28:
            lows += 1
        contradiction_penalty = min(.18, lows * .07)

    confidence = max(0.0, min(.97, weighted + agreement_boost - contradiction_penalty))

    if confidence >= .82 and agreement_count >= 2:
        verdict = "strong_match"
    elif confidence >= .66:
        verdict = "likely_match"
    elif confidence >= .46:
        verdict = "possible_match"
    else:
        verdict = "not_verified"

    contributions = {
        k: round((values[k] * WEIGHTS[k] / max(denom, 1e-9)) if available[k] else 0.0, 4)
        for k in WEIGHTS
    }
    return VerificationResult(
        confidence=confidence,
        verdict=verdict,
        agreement_count=agreement_count,
        contradiction_penalty=contradiction_penalty,
        contributions=contributions,
    )
