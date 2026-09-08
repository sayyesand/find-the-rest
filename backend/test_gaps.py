from app.gaps import detect_chain_gaps, build_gap_queries
from app.models import Candidate, ChainNode

def node(part):
    c = Candidate(
        title=f"Story Part {part}",
        url=f"https://example.com/p{part}",
        platform="web",
        reason="continuation",
        score=.7,
        evidence={"continuation_signal": .8},
    )
    return ChainNode(
        candidate=c,
        inferred_part=part,
        relationship="continuation",
        chain_score=.7,
        order_reason="test",
    )

def test_detects_single_gap():
    gaps = detect_chain_gaps([node(2), node(4)])
    assert [g.missing_part for g in gaps] == [3]

def test_detects_multiple_gaps_bounded():
    gaps = detect_chain_gaps([node(2), node(7)])
    assert [g.missing_part for g in gaps] == [3,4,5,6]

def test_no_gap_for_consecutive_parts():
    assert detect_chain_gaps([node(2), node(3), node(4)]) == []

def test_build_gap_query_targets_exact_missing_part():
    gaps = detect_chain_gaps([node(2), node(4)])
    qs = build_gap_queries(
        gaps,
        source_title="Maya bridge rescue",
        source_description="Route 66 dog rescue",
        creator="RescueDaily",
        fingerprint_terms=["Maya","Route 66","bridge"],
    )
    assert len(qs) == 1
    part, query = qs[0]
    assert part == 3
    assert '"part 3"' in query
    assert '"RescueDaily"' in query
