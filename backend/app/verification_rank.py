from dataclasses import dataclass

from .models import Candidate, MultimodalVerifyResponse


@dataclass(frozen=True)
class VerificationAdjustment:
    candidate: Candidate
    adjusted_score: float
    delta: float
    disposition: str
    verification_confidence: float
    verdict: str


def fuse_candidate_verification(
    candidate: Candidate,
    verification: MultimodalVerifyResponse | None,
    *,
    provider_status: str = "ok",
) -> VerificationAdjustment:
    """Fuse media verification into ranking without allowing it to erase story/provenance evidence.

    The candidate's original score remains intact. This produces a separate adjusted
    score used only for verification-aware reranking.
    """
    base = float(candidate.score)
    if verification is None or provider_status != "ok":
        return VerificationAdjustment(
            candidate=candidate,
            adjusted_score=base,
            delta=0.0,
            disposition="unverified",
            verification_confidence=0.0,
            verdict="unavailable",
        )

    confidence = max(0.0, min(1.0, float(verification.confidence)))
    verdict = verification.verdict
    contradiction = max(0.0, min(1.0, float(verification.contradiction_penalty)))

    # Strong corroboration can help, but only within a bounded range. Search/story
    # evidence remains materially relevant to the final ordering.
    if verdict == "strong_match":
        delta = 0.10 + max(0.0, confidence - 0.82) * 0.20
        disposition = "promote"
    elif verdict == "likely_match":
        delta = 0.05 + max(0.0, confidence - 0.66) * 0.10
        disposition = "promote"
    elif verdict == "possible_match":
        delta = -0.015 if confidence < 0.56 else 0.01
        disposition = "hold"
    else:
        # A failed verification is negative evidence, not proof of unrelatedness.
        # Demotion becomes stronger when the verifier itself is confident or reports
        # contradictions, but is capped to avoid erasing strong provenance/story clues.
        delta = -(0.08 + min(0.12, (1.0 - confidence) * 0.10 + contradiction * 0.25))
        disposition = "demote"

    adjusted = max(0.0, min(0.99, base + delta))
    return VerificationAdjustment(
        candidate=candidate,
        adjusted_score=round(adjusted, 4),
        delta=round(adjusted - base, 4),
        disposition=disposition,
        verification_confidence=round(confidence, 4),
        verdict=verdict,
    )


def rerank_verified_candidates(
    items: list[tuple[Candidate, MultimodalVerifyResponse | None, str]],
) -> list[VerificationAdjustment]:
    adjusted = [
        fuse_candidate_verification(candidate, verification, provider_status=status)
        for candidate, verification, status in items
    ]
    # Preserve original ranking as stable tie-breaker.
    order = {str(candidate.url): i for i, (candidate, _, _) in enumerate(items)}
    return sorted(
        adjusted,
        key=lambda x: (-x.adjusted_score, order.get(str(x.candidate.url), 9999)),
    )
