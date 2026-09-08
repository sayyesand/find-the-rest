from dataclasses import dataclass

from .media import compare_media
from .semantic import compare_semantics

@dataclass(frozen=True)
class LinkEvidence:
    visual: float
    audio: float
    transcript: float
    scene: float
    confidence: float
    verified: bool

def verify_link(
    source_path: str,
    candidate_path: str,
    *,
    source_transcript: str | None = None,
    candidate_transcript: str | None = None,
) -> LinkEvidence:
    media = compare_media(source_path, candidate_path)
    semantic = compare_semantics(
        source_path,
        candidate_path,
        source_transcript=source_transcript,
        candidate_transcript=candidate_transcript,
    )

    # Do not punish absent audio/transcripts as harshly as contradictory evidence.
    signals = []
    if media.visual > 0:
        signals.append((media.visual, 0.30))
    if media.audio > 0:
        signals.append((media.audio, 0.15))
    if semantic.transcript > 0:
        signals.append((semantic.transcript, 0.35))
    if semantic.scene > 0:
        signals.append((semantic.scene, 0.20))

    if not signals:
        confidence = 0.0
    else:
        weight = sum(w for _, w in signals)
        confidence = sum(v * w for v, w in signals) / weight

    # A strong seam or strong semantic continuation can verify a link; weak generic
    # scene resemblance alone cannot.
    strong_content = max(media.visual, media.audio, semantic.transcript) >= 0.58
    corroborated = sum(1 for v, _ in signals if v >= 0.42) >= 2
    verified = confidence >= 0.50 and (strong_content or corroborated)

    return LinkEvidence(
        visual=media.visual,
        audio=media.audio,
        transcript=semantic.transcript,
        scene=semantic.scene,
        confidence=min(0.99, max(0.0, confidence)),
        verified=verified,
    )

def chain_confidence(links: list[LinkEvidence]) -> float:
    if not links:
        return 0.0
    scores = [x.confidence for x in links]
    weakest = min(scores)
    mean = sum(scores) / len(scores)
    # Chains are only as trustworthy as their weakest transition.
    return min(0.99, weakest * 0.55 + mean * 0.45)
