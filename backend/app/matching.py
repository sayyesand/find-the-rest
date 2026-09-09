import html
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher

STOPWORDS = {
    "the","and","for","that","this","with","from","you","your","are","was","were","have","has","had",
    "but","not","what","when","where","who","why","how","into","out","part","pt","video","shorts","short",
    "official","full","episode","clip","watch","more","about","they","their","there","then","than","just",
}

PART_RE = re.compile(r"\b(?:part|pt)\.?\s*(\d+|ii|iii|iv)\b", re.I)
CONTINUATION_PHRASES = (
    "part 2", "part two", "pt 2", "pt. 2", "continued", "continuation", "the rest",
    "what happened next", "update", "follow up", "follow-up",
)

GENERIC_TITLE_TERMS = {
    "remaster", "remastered", "music", "song", "audio", "lyrics", "lyric",
    "version", "original", "official", "video", "clip", "episode", "full",
}


def clean_text(text: str) -> str:
    text = html.unescape(text or "").lower()
    text = PART_RE.sub(" ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def tokens(text: str) -> set[str]:
    return {w for w in clean_text(text).split() if len(w) > 2 and w not in STOPWORDS}


def text_similarity(source_title: str, source_description: str, candidate_title: str, candidate_description: str) -> float:
    source = clean_text(f"{source_title} {source_description}")
    candidate = clean_text(f"{candidate_title} {candidate_description}")
    a, b = tokens(source), tokens(candidate)
    jaccard = len(a & b) / max(len(a | b), 1)
    sequence = SequenceMatcher(None, source[:500], candidate[:500]).ratio() if source and candidate else 0.0
    return min(1.0, 0.72 * jaccard + 0.28 * sequence)


def continuation_signal(title: str, description: str) -> float:
    raw = f"{title} {description}".lower()
    match = PART_RE.search(raw)
    if match:
        value = match.group(1).lower()
        if value in {"2", "ii"}:
            return 1.0
        return 0.55
    if any(p in raw for p in CONTINUATION_PHRASES):
        return 0.72
    return 0.0


def _part_number(text: str) -> int | None:
    match = PART_RE.search(text or "")
    if not match:
        return None
    value = match.group(1).lower()
    return {"ii": 2, "iii": 3, "iv": 4}.get(value, int(value) if value.isdigit() else None)


def credible_continuation(
    *,
    source_title: str,
    source_creator: str | None,
    candidate: "Candidate",
) -> bool:
    """Require story identity as well as generic continuation metadata.

    Same-creator and later-publication signals are useful ranking clues, but they
    cannot turn another unrelated upload by that creator into a continuation.
    """
    source_terms = tokens(source_title) - tokens(source_creator or "") - GENERIC_TITLE_TERMS
    candidate_terms = tokens(candidate.title) - tokens(candidate.creator or "") - GENERIC_TITLE_TERMS
    shared_topic_terms = source_terms & candidate_terms

    source_part = _part_number(source_title)
    candidate_part = _part_number(candidate.title)
    if source_part is not None and candidate_part is not None:
        return candidate_part > source_part and bool(shared_topic_terms)

    numbered_follow_up = (
        candidate_part is not None
        and (source_part is None or candidate_part > source_part)
        and bool(shared_topic_terms)
    )

    title_continuation = continuation_signal(candidate.title, "")
    explicitly_named_follow_up = title_continuation >= 0.7 and bool(shared_topic_terms)

    evidence = candidate.evidence or {}
    direct_identity = max(
        float(evidence.get("reverse_image_match", 0.0) or 0.0),
        float(evidence.get("robust_visual", 0.0) or 0.0),
        float(evidence.get("visual_continuity", 0.0) or 0.0),
        float(evidence.get("audio_fingerprint", 0.0) or 0.0),
        float(evidence.get("audio_continuity", 0.0) or 0.0),
        float(evidence.get("transcript_semantic", 0.0) or 0.0),
        float(evidence.get("scene_semantic", 0.0) or 0.0),
    )
    content_verified_follow_up = direct_identity >= 0.6 and (
        title_continuation >= 0.55
        or float(evidence.get("ending_continuity", 0.0) or 0.0) >= 0.55
    )

    return numbered_follow_up or explicitly_named_follow_up or content_verified_follow_up


def consecutive_numbered_continuation(
    *,
    source_title: str,
    source_creator: str | None,
    candidate: "Candidate",
) -> bool:
    """Recognize an explicit next part while retaining story and creator anchors."""
    source_part = _part_number(source_title)
    candidate_part = _part_number(candidate.title)
    if source_part is None or candidate_part != source_part + 1:
        return False

    source_terms = tokens(source_title) - tokens(source_creator or "") - GENERIC_TITLE_TERMS
    candidate_terms = tokens(candidate.title) - tokens(candidate.creator or "") - GENERIC_TITLE_TERMS
    if not (source_terms & candidate_terms):
        return False

    creator_match = float((candidate.evidence or {}).get("creator_match", 0.0) or 0.0)
    return creator_match >= 0.8


def creator_similarity(source_creator: str | None, candidate_creator: str | None) -> float:
    if not source_creator or not candidate_creator:
        return 0.0
    a = clean_text(source_creator)
    b = clean_text(candidate_creator)
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def sequence_signal(source_published: str | None, candidate_published: str | None) -> float:
    source = parse_datetime(source_published)
    candidate = parse_datetime(candidate_published)
    if not source or not candidate:
        return 0.0
    delta_hours = (candidate - source).total_seconds() / 3600
    if delta_hours <= 0:
        return 0.0
    # Continuations are often posted quickly, but preserve some credit for later follow-ups.
    return max(0.0, min(1.0, math.exp(-delta_hours / (24 * 10))))


@dataclass
class Evidence:
    text: float
    continuation: float
    creator: float
    sequence: float
    visual: float = 0.0
    audio: float = 0.0
    transcript: float = 0.0
    scene: float = 0.0

    @property
    def score(self) -> float:
        # Metadata-only ceiling avoids claiming near-certainty until content evidence exists.
        metadata = (
            self.text * 0.34
            + self.continuation * 0.24
            + self.creator * 0.22
            + self.sequence * 0.20
        )
        has_content = self.visual > 0 or self.audio > 0 or self.transcript > 0 or self.scene > 0
        if not has_content:
            return min(0.84, metadata)
        # Fuse available content evidence with metadata instead of diluting a strong
        # metadata match when only some media signals are present. Missing signals do
        # not count as zeros; only evidence actually computed participates.
        weighted = []
        if self.visual > 0:
            weighted.append((self.visual, 0.24))
        if self.audio > 0:
            weighted.append((self.audio, 0.16))
        if self.transcript > 0:
            weighted.append((self.transcript, 0.34))
        if self.scene > 0:
            weighted.append((self.scene, 0.26))
        weight_sum = sum(w for _, w in weighted)
        content = sum(v * w for v, w in weighted) / max(weight_sum, 1e-9)
        # Content can substantially raise confidence but cannot erase contradictory
        # metadata entirely. Perfect corroborating content approaches certainty.
        total = metadata + (1.0 - metadata) * 0.72 * content
        return min(0.99, total)

    def as_dict(self) -> dict[str, float]:
        return {
            "text_similarity": round(self.text, 4),
            "continuation_signal": round(self.continuation, 4),
            "creator_match": round(self.creator, 4),
            "sequence_signal": round(self.sequence, 4),
            "visual_continuity": round(self.visual, 4),
            "audio_continuity": round(self.audio, 4),
            "transcript_semantic": round(self.transcript, 4),
            "scene_semantic": round(self.scene, 4),
        }
