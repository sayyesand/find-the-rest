from dataclasses import dataclass

from .models import Candidate


@dataclass(frozen=True)
class ConfidenceProfile:
    calibrated: float
    grade: str
    family_count: int
    strong_family_count: int
    families: dict[str, float]
    metadata_only: bool
    cap: float


def _max(ev: dict[str, float], *keys: str) -> float:
    return max((float(ev.get(k, 0.0) or 0.0) for k in keys), default=0.0)


def confidence_profile(candidate: Candidate) -> ConfidenceProfile:
    ev = candidate.evidence or {}

    families = {
        # Closely related text clues are deliberately collapsed into one family.
        "story_semantics": _max(ev, "text_similarity", "story_fingerprint", "ending_continuity"),
        "continuation": _max(ev, "continuation_signal"),
        "creator": _max(ev, "creator_match", "trace_creator_authority"),
        "chronology": _max(ev, "sequence_signal", "trace_earlier_upload"),
        "provenance": max(candidate.trace_score, _max(ev, "trace_textual_originality", "trace_duration_advantage")),
        "visual_identity": _max(ev, "reverse_image_match", "robust_visual", "visual_continuity"),
        "audio_identity": _max(ev, "audio_fingerprint", "audio_continuity"),
        "transcript": _max(ev, "transcript_semantic"),
        "scene": _max(ev, "scene_semantic"),
    }
    families = {k: max(0.0, min(1.0, v)) for k, v in families.items() if v > 0.0}

    family_count = sum(1 for v in families.values() if v >= .18)
    strong_count = sum(1 for v in families.values() if v >= .55)
    direct = any(k in families and families[k] >= .45 for k in ("visual_identity", "audio_identity", "transcript", "scene"))
    metadata_only = not direct

    # Independent-evidence caps. Many variants of the same text clue cannot create
    # high confidence by themselves.
    if family_count <= 1:
        cap = .42
    elif family_count == 2:
        cap = .58
    elif metadata_only:
        cap = .84
    else:
        cap = .96

    # A pile of weak signals remains weak even when many fields are populated.
    if strong_count == 0:
        cap = min(cap, .48)
    elif strong_count == 1 and metadata_only:
        cap = min(cap, .68)

    # Contradictions are already reflected in candidate.score, but this additional
    # ceiling prevents a candidate with a large contradiction flag being presented
    # as highly certain after later intent/provenance bonuses.
    contradiction = _max(ev, "contradiction_penalty")
    if contradiction >= .28:
        cap = min(cap, .54)
    elif contradiction >= .16:
        cap = min(cap, .68)

    calibrated = max(0.0, min(candidate.score, cap))

    if calibrated >= .78 and strong_count >= 2 and family_count >= 3:
        grade = "high"
    elif calibrated >= .58 and strong_count >= 1 and family_count >= 2:
        grade = "moderate"
    elif calibrated >= .44:
        grade = "tentative"
    else:
        grade = "low"

    return ConfidenceProfile(
        calibrated=round(calibrated, 4),
        grade=grade,
        family_count=family_count,
        strong_family_count=strong_count,
        families={k: round(v, 4) for k, v in families.items()},
        metadata_only=metadata_only,
        cap=round(cap, 4),
    )


def annotate_confidence(candidate: Candidate) -> Candidate:
    profile = confidence_profile(candidate)
    ev = dict(candidate.evidence)
    ev.update({
        "calibrated_confidence": profile.calibrated,
        "evidence_family_count": float(profile.family_count),
        "strong_family_count": float(profile.strong_family_count),
        "confidence_cap": profile.cap,
    })
    return candidate.model_copy(update={"evidence": ev})
