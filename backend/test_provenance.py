from app.models import Candidate
from app.provenance import build_provenance_graph


def candidate(title, url, score, *, role=None, trace=.0, creator="Creator", published=None, evidence=None):
    return Candidate(
        title=title,
        url=url,
        platform="web",
        creator=creator,
        published_at=published,
        reason="test",
        score=score,
        evidence=evidence or {},
        trace_role=role,
        trace_score=trace,
    )


def test_likely_original_points_to_shared_source():
    original = candidate(
        "Full original video",
        "https://example.com/full",
        .72,
        role="likely_original",
        trace=.82,
        published="2025-01-01T00:00:00+00:00",
        evidence={"trace_earlier_upload": .75},
    )
    graph = build_provenance_graph(
        source_url="https://social.example/clip",
        source_creator=None,
        source_published_at="2025-02-01T00:00:00+00:00",
        candidates=[original],
    )
    assert graph.likely_origin_node_id
    assert any(e.relationship == "likely_source_of" and e.to_id == "source" for e in graph.edges)


def test_continuation_edge_starts_at_shared_source():
    cont = candidate(
        "The story continues",
        "https://example.com/part2",
        .68,
        creator="Creator",
        evidence={"continuation_signal": .9, "story_fingerprint": .7},
    )
    graph = build_provenance_graph(
        source_url="https://example.com/part1",
        source_creator="Creator",
        source_published_at=None,
        candidates=[cont],
    )
    assert any(e.from_id == "source" and e.relationship == "continues_as" for e in graph.edges)


def test_fragment_is_attached_to_likely_original():
    original = candidate("Full version", "https://example.com/full", .75, role="likely_original", trace=.85)
    fragment = candidate("Short clip", "https://example.com/clip2", .52, role="fragment", trace=.2)
    graph = build_provenance_graph(
        source_url="https://example.com/shared",
        source_creator=None,
        source_published_at=None,
        candidates=[original, fragment],
    )
    origin_id = graph.likely_origin_node_id
    assert any(e.from_id == origin_id and e.relationship == "excerpt_or_fragment" for e in graph.edges)


def test_low_score_candidates_do_not_pollute_graph():
    weak = candidate("Maybe related", "https://example.com/weak", .12)
    graph = build_provenance_graph(
        source_url="https://example.com/source",
        source_creator=None,
        source_published_at=None,
        candidates=[weak],
    )
    assert len(graph.nodes) == 1
    assert not graph.edges
