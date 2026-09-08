from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from .models import Candidate
from .hunter import canonical_url, classify_candidate


@dataclass(frozen=True)
class ProvenanceNode:
    node_id: str
    label: str
    url: str
    role: str
    score: float
    creator: str | None = None
    published_at: str | None = None


@dataclass(frozen=True)
class ProvenanceEdge:
    from_id: str
    to_id: str
    relationship: str
    confidence: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ProvenanceGraph:
    nodes: tuple[ProvenanceNode, ...]
    edges: tuple[ProvenanceEdge, ...]
    likely_origin_node_id: str | None
    confidence: float


def _node_id(url: str) -> str:
    return canonical_url(url)


def _parse_time(raw: str | None):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _candidate_role(candidate: Candidate, source_creator: str | None) -> str:
    if candidate.trace_role == "likely_original":
        return "likely_original"
    if candidate.trace_role == "fragment":
        return "fragment"
    if candidate.trace_role == "likely_repost":
        return "likely_repost"
    kind = classify_candidate(source_creator, candidate)
    ev = candidate.evidence or {}
    continuation_strength = max(
        ev.get("continuation_signal", 0.0),
        ev.get("ending_continuity", 0.0),
    )
    if kind == "full_original":
        return "likely_original"
    if kind == "official_continuation" or (continuation_strength >= .55 and ev.get("story_fingerprint", 0.0) >= .25):
        return "continuation"
    if kind == "continuation_repost":
        return "continuation_repost"
    return "related"


def _same_creator(a: Candidate, b: Candidate) -> bool:
    if not a.creator or not b.creator:
        return False
    return a.creator.strip().lower() == b.creator.strip().lower()


def build_provenance_graph(
    *,
    source_url: str,
    source_creator: str | None,
    source_published_at: str | None,
    candidates: list[Candidate],
) -> ProvenanceGraph:
    source_id = "source"
    nodes = [ProvenanceNode(
        node_id=source_id,
        label="Shared source",
        url=source_url,
        role="source",
        score=1.0,
        creator=source_creator,
        published_at=source_published_at,
    )]

    eligible = [c for c in candidates[:10] if c.score >= 0.24]
    for c in eligible:
        nodes.append(ProvenanceNode(
            node_id=_node_id(str(c.url)),
            label=c.title[:140],
            url=str(c.url),
            role=_candidate_role(c, source_creator),
            score=c.score,
            creator=c.creator,
            published_at=c.published_at,
        ))

    edges: list[ProvenanceEdge] = []
    originals = [c for c in eligible if _candidate_role(c, source_creator) == "likely_original"]
    likely_origin = max(originals, key=lambda c: (c.trace_score, c.score), default=None)

    # Strongest original-like candidate may explain the source as an excerpt/repost.
    if likely_origin:
        reasons = ["candidate has original/full-source evidence"]
        if likely_origin.duration_seconds:
            reasons.append("candidate is longer than the shared source or other fragments")
        if likely_origin.evidence.get("trace_earlier_upload", 0) >= .5:
            reasons.append("candidate appears substantially earlier")
        edges.append(ProvenanceEdge(
            from_id=_node_id(str(likely_origin.url)),
            to_id=source_id,
            relationship="likely_source_of",
            confidence=min(.94, max(.45, likely_origin.trace_score * .72 + likely_origin.score * .28)),
            reasons=tuple(reasons),
        ))

    for c in eligible:
        cid = _node_id(str(c.url))
        role = _candidate_role(c, source_creator)
        ev = c.evidence or {}

        if role in {"continuation", "continuation_repost"}:
            conf = min(.92, max(.34, c.score * .72 + ev.get("continuation_signal", 0) * .18 + ev.get("story_fingerprint", 0) * .10))
            reasons = ["candidate continues the same story/topic"]
            if ev.get("continuation_signal", 0) > .5:
                reasons.append("continuation wording supports the relationship")
            if ev.get("story_fingerprint", 0) > .4:
                reasons.append("story details overlap")
            edges.append(ProvenanceEdge(
                from_id=source_id,
                to_id=cid,
                relationship="continues_as" if role == "continuation" else "continues_via_repost",
                confidence=conf,
                reasons=tuple(reasons),
            ))
            continue

        if role in {"fragment", "likely_repost"}:
            parent_id = _node_id(str(likely_origin.url)) if likely_origin and str(likely_origin.url) != str(c.url) else source_id
            conf = min(.90, max(.30, c.score * .65 + ev.get("reverse_image_match", 0) * .20 + ev.get("story_fingerprint", 0) * .15))
            relation = "excerpt_or_fragment" if role == "fragment" else "likely_repost_of"
            edges.append(ProvenanceEdge(
                from_id=parent_id,
                to_id=cid,
                relationship=relation,
                confidence=conf,
                reasons=("source-tracing role suggests derivative media",),
            ))
            continue

        # Same-creator, later related posts are useful lineage context, but remain weak.
        if likely_origin and _same_creator(likely_origin, c):
            a = _parse_time(likely_origin.published_at)
            b = _parse_time(c.published_at)
            if not a or not b or b >= a:
                edges.append(ProvenanceEdge(
                    from_id=_node_id(str(likely_origin.url)),
                    to_id=cid,
                    relationship="same_creator_related",
                    confidence=min(.66, max(.28, c.score * .55)),
                    reasons=("same creator and related story evidence",),
                ))

    # Deduplicate equivalent directed relationships.
    dedup: dict[tuple[str, str, str], ProvenanceEdge] = {}
    for edge in edges:
        key = (edge.from_id, edge.to_id, edge.relationship)
        old = dedup.get(key)
        if old is None or edge.confidence > old.confidence:
            dedup[key] = edge
    edges = sorted(dedup.values(), key=lambda e: e.confidence, reverse=True)[:16]

    graph_conf = 0.0
    if edges:
        top = [e.confidence for e in edges[:3]]
        graph_conf = min(.94, sum(top) / len(top))
    return ProvenanceGraph(
        nodes=tuple(nodes),
        edges=tuple(edges),
        likely_origin_node_id=_node_id(str(likely_origin.url)) if likely_origin else None,
        confidence=graph_conf,
    )
