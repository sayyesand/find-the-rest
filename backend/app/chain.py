import re
from dataclasses import dataclass

from .models import Candidate, ChainNode
from .matching import clean_text, parse_datetime

PART_PATTERNS = (
    re.compile(r"\b(?:part|pt)\.?\s*(\d{1,2})\b", re.I),
)
EPISODE_RE = re.compile(r"\b(?:episode|ep)\.?\s*(\d{1,3})\b", re.I)
ROMAN_RE = re.compile(r"\b(?:part|pt)\.?\s*(ii|iii|iv|v|vi|vii|viii|ix|x)\b", re.I)
ROMAN = {"ii":2,"iii":3,"iv":4,"v":5,"vi":6,"vii":7,"viii":8,"ix":9,"x":10}

UPDATE_TERMS = ("update", "follow up", "follow-up", "what happened next", "afterward", "afterwards")
ORIGINAL_TERMS = ("full original", "original source", "complete video", "full video", "uncut", "entire video")

def infer_part(candidate: Candidate) -> int | None:
    text = f"{candidate.title} {candidate.snippet or ''}"
    for pattern in PART_PATTERNS:
        m = pattern.search(text)
        if m:
            try:
                value = int(m.group(1))
                return value if 1 <= value <= 100 else None
            except ValueError:
                pass
    m = ROMAN_RE.search(text)
    if m:
        return ROMAN.get(m.group(1).lower())
    return None


def infer_episode(candidate: Candidate) -> int | None:
    text = f"{candidate.title} {candidate.snippet or ''}"
    m = EPISODE_RE.search(text)
    if not m:
        return None
    try:
        value = int(m.group(1))
        return value if 1 <= value <= 999 else None
    except ValueError:
        return None

def relationship(candidate: Candidate) -> str:
    text = clean_text(f"{candidate.title} {candidate.snippet or ''}")
    if candidate.trace_role == "likely_original" or any(x in text for x in ORIGINAL_TERMS):
        return "full_original"
    if any(x in text for x in UPDATE_TERMS):
        return "update"
    if infer_part(candidate) and infer_part(candidate) >= 2:
        return "continuation"
    if candidate.evidence.get("continuation_signal", 0.0) >= 0.55:
        return "continuation"
    return "related"

def _chain_score(candidate: Candidate) -> float:
    evidence = candidate.evidence
    contradiction = evidence.get("contradiction_penalty", 0.0)
    story = evidence.get("story_fingerprint", 0.0)
    ending = evidence.get("ending_continuity", 0.0)
    continuation = evidence.get("continuation_signal", 0.0)
    creator = evidence.get("creator_match", 0.0)
    base = candidate.score * 0.58 + story * 0.15 + ending * 0.12 + continuation * 0.10 + creator * 0.05
    return max(0.0, min(0.99, base - contradiction * 0.35))

def build_continuation_chain(candidates: list[Candidate], *, max_nodes: int = 6) -> tuple[list[ChainNode], float]:
    eligible: list[tuple[Candidate, int | None, int | None, str, float]] = []
    for c in candidates:
        rel = relationship(c)
        score = _chain_score(c)
        contradiction = c.evidence.get("contradiction_penalty", 0.0)
        if score < 0.34 or contradiction >= 0.38:
            continue
        if rel == "related" and score < 0.52:
            continue
        eligible.append((c, infer_part(c), infer_episode(c), rel, score))

    # For explicit part duplicates, choose strongest evidence before chronology.
    strongest_by_part: dict[int, tuple[Candidate, int | None, int | None, str, float]] = {}
    no_part: list[tuple[Candidate, int | None, int | None, str, float]] = []
    for item in eligible:
        c, part, episode, rel, score = item
        if part is None:
            no_part.append(item)
            continue
        previous = strongest_by_part.get(part)
        if previous is None:
            strongest_by_part[part] = item
        else:
            prev_c, _, _, _, prev_score = previous
            prev_creator = prev_c.evidence.get("creator_match", 0.0)
            creator = c.evidence.get("creator_match", 0.0)
            if (score, creator) > (prev_score, prev_creator):
                strongest_by_part[part] = item
    eligible = list(strongest_by_part.values()) + no_part

    def order_key(item):
        c, part, episode, rel, score = item
        dt = parse_datetime(c.published_at)
        timestamp = dt.timestamp() if dt else float("inf")
        if rel == "full_original":
            bucket = 0
            sequence = 0
        elif part is not None:
            bucket = 1
            sequence = part
        elif rel in {"continuation", "update"} and episode is not None:
            bucket = 2
            sequence = episode
        elif rel in {"continuation", "update"}:
            bucket = 3
            sequence = 9999
        else:
            bucket = 4
            sequence = 9999
        return (bucket, sequence, timestamp, -score)

    eligible.sort(key=order_key)

    nodes: list[ChainNode] = []
    for c, part, episode, rel, score in eligible:
        if rel == "full_original":
            reason = "Likely full/original source; placed before segmented continuations."
        elif part is not None:
            reason = f"Explicitly identifies as part {part}."
        elif episode is not None and rel in {"continuation", "update"}:
            reason = f"Episode {episode}; treated as episode context, not as Part {episode}."
        elif c.published_at:
            reason = "Continuation/update without a reliable part number; ordered by publication time."
        else:
            reason = "Continuation/update without a reliable part number."
        nodes.append(ChainNode(
            candidate=c,
            inferred_part=part,
            episode_number=episode,
            relationship=rel,
            chain_score=round(score, 4),
            order_reason=reason,
        ))
        if len(nodes) >= max_nodes:
            break

    if not nodes:
        return [], 0.0
    scores = sorted((n.chain_score for n in nodes), reverse=True)
    top = scores[0]
    mean = sum(scores) / len(scores)
    confidence = min(0.94, top * 0.62 + mean * 0.38)
    return nodes, round(confidence, 4)

