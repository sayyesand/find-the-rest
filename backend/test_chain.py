from app.chain import infer_part, infer_episode, relationship, build_continuation_chain
from app.models import Candidate

def c(title, score=.62, published=None, reason="", continuation=.8, contradiction=0.0, trace_role=None):
    return Candidate(
        title=title,
        url="https://example.com/" + title.replace(" ","_"),
        platform="web",
        published_at=published,
        reason=reason,
        score=score,
        evidence={
            "continuation_signal": continuation,
            "story_fingerprint": .55,
            "ending_continuity": .45,
            "creator_match": .2,
            "contradiction_penalty": contradiction,
        },
        trace_role=trace_role,
    )

def test_infer_numeric_and_roman_parts():
    assert infer_part(c("Storm drain Part 2")) == 2
    assert infer_part(c("Storm drain Pt. III")) == 3

def test_chain_orders_explicit_parts():
    items = [
        c("Story Part 3", published="2026-01-03T00:00:00Z"),
        c("Story Part 2", published="2026-01-02T00:00:00Z"),
        c("Story Part 4", published="2026-01-04T00:00:00Z"),
    ]
    chain, confidence = build_continuation_chain(items)
    assert [n.inferred_part for n in chain] == [2,3,4]
    assert confidence > 0

def test_duplicate_part_keeps_one_node():
    items = [
        c("Story Part 2", score=.70),
        c("Repost Story Part 2", score=.52),
        c("Story Part 3", score=.65),
    ]
    chain, _ = build_continuation_chain(items)
    assert [n.inferred_part for n in chain].count(2) == 1

def test_strong_contradiction_excluded_from_chain():
    good = c("Story Part 2", contradiction=.05)
    bad = c("Unrelated Part 3", contradiction=.45)
    chain, _ = build_continuation_chain([good,bad])
    assert len(chain) == 1
    assert chain[0].candidate.title == "Story Part 2"

def test_full_original_gets_distinct_relationship():
    original = c("Full original complete video", reason="full original source", trace_role="likely_original")
    chain, _ = build_continuation_chain([original])
    assert chain[0].relationship == "full_original"
    assert chain[0].inferred_part is None


def test_episode_number_is_not_part_number():
    item = c("Stories From India Episode 248", continuation=.8)
    assert infer_part(item) is None
    assert infer_episode(item) == 248
    chain, _ = build_continuation_chain([item])
    assert chain[0].inferred_part is None
    assert chain[0].episode_number == 248

def test_duplicate_part_keeps_strongest_not_earliest():
    items = [
        c("Story Part 2", score=.52, published="2026-01-01T00:00:00Z"),
        c("Story Part 2 official", score=.78, published="2026-01-02T00:00:00Z"),
        c("Story Part 3", score=.65, published="2026-01-03T00:00:00Z"),
    ]
    chain, _ = build_continuation_chain(items)
    part2 = next(n for n in chain if n.inferred_part == 2)
    assert part2.candidate.title == "Story Part 2 official"
