import re
from datetime import datetime
from dataclasses import dataclass, replace

from .models import Candidate
from .matching import clean_text, creator_similarity, parse_datetime

ORIGINAL_TERMS = (
    "original", "original source", "full video", "full version", "complete video",
    "complete story", "uncut", "extended", "entire video", "full episode",
)
REPOST_TERMS = ("repost", "credit", "credits", "via", "source:", "stolen", "mirror")
FRAGMENT_TERMS = ("part 1", "pt 1", "part one", "clip", "short", "excerpt", "preview")

@dataclass(frozen=True)
class TraceEvidence:
    textual_originality: float = 0.0
    duration_advantage: float = 0.0
    earlier_upload: float = 0.0
    creator_authority: float = 0.0
    fragment_penalty: float = 0.0

    @property
    def score(self) -> float:
        positive = (
            self.textual_originality * 0.36
            + self.duration_advantage * 0.30
            + self.earlier_upload * 0.16
            + self.creator_authority * 0.18
        )
        return max(0.0, min(1.0, positive - self.fragment_penalty * 0.22))

    def as_dict(self) -> dict[str, float]:
        return {
            "textual_originality": round(self.textual_originality, 4),
            "duration_advantage": round(self.duration_advantage, 4),
            "earlier_upload": round(self.earlier_upload, 4),
            "creator_authority": round(self.creator_authority, 4),
            "fragment_penalty": round(self.fragment_penalty, 4),
        }

def _contains(text: str, terms: tuple[str, ...]) -> bool:
    raw = text.lower()
    return any(term in raw for term in terms)

def _duration_advantage(source_duration: float | None, candidate_duration: float | None) -> float:
    if not source_duration or not candidate_duration or source_duration <= 0:
        return 0.0
    ratio = candidate_duration / source_duration
    if ratio >= 3.0:
        return 1.0
    if ratio >= 2.0:
        return 0.8
    if ratio >= 1.5:
        return 0.58
    if ratio >= 1.2:
        return 0.28
    return 0.0

def _earlier_upload(source_published: str | None, candidate_published: str | None) -> float:
    source = parse_datetime(source_published)
    candidate = parse_datetime(candidate_published)
    if not source or not candidate or candidate >= source:
        return 0.0
    days = (source - candidate).total_seconds() / 86400
    if days >= 30:
        return 1.0
    if days >= 7:
        return 0.75
    if days >= 1:
        return 0.5
    return 0.25

def trace_candidate(
    candidate: Candidate,
    *,
    source_creator: str | None,
    source_duration: float | None,
    source_published: str | None,
) -> Candidate:
    text = f"{candidate.title} {candidate.snippet or ''}"
    explicit_original = 1.0 if _contains(text, ORIGINAL_TERMS) else 0.0
    repost_hint = 0.55 if _contains(text, REPOST_TERMS) else 0.0
    fragment = 1.0 if _contains(text, FRAGMENT_TERMS) else 0.0

    creator = creator_similarity(source_creator, candidate.creator)
    # Same creator is useful authority evidence but is deliberately not proof of originality.
    authority = 0.65 if creator >= 0.92 else 0.0

    ev = TraceEvidence(
        textual_originality=max(explicit_original, repost_hint * 0.25),
        duration_advantage=_duration_advantage(source_duration, candidate.duration_seconds),
        earlier_upload=_earlier_upload(source_published, candidate.published_at),
        creator_authority=authority,
        fragment_penalty=fragment,
    )
    score = ev.score

    role = "related"
    if explicit_original and score >= 0.30:
        role = "likely_original"
    elif ev.duration_advantage >= 0.58 and candidate.evidence.get("text_similarity", 0.0) >= 0.30 and score >= 0.25:
        role = "likely_original"
    elif fragment >= 1.0:
        role = "fragment"
    elif repost_hint > 0:
        role = "likely_repost"

    evidence = dict(candidate.evidence)
    evidence.update({f"trace_{k}": v for k, v in ev.as_dict().items()})
    return candidate.model_copy(update={
        "trace_role": role,
        "trace_score": round(score, 4),
        "evidence": evidence,
    })

def trace_and_promote(
    candidates: list[Candidate],
    *,
    source_creator: str | None,
    source_duration: float | None,
    source_published: str | None,
) -> list[Candidate]:
    traced = [
        trace_candidate(
            c,
            source_creator=source_creator,
            source_duration=source_duration,
            source_published=source_published,
        )
        for c in candidates
    ]

    def rank(c: Candidate) -> float:
        # Originality is a secondary signal. It can break close contests, but cannot
        # rescue a weak topical match into first place.
        original_bonus = min(0.12, c.trace_score * 0.12) if c.trace_role == "likely_original" else 0.0
        fragment_penalty = 0.04 if c.trace_role == "fragment" else 0.0
        return c.score + original_bonus - fragment_penalty

    return sorted(traced, key=rank, reverse=True)
