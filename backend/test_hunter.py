from app.hunter import canonical_url, compact_seed, build_search_plans, classify_candidate, merge_ranked
from app.models import Candidate

def cand(url, title, score, creator=None, reason=""):
    return Candidate(title=title, url=url, platform="youtube", creator=creator, reason=reason, score=score)

def test_canonical_url_strips_tracking():
    a = canonical_url("https://www.youtube.com/watch?v=abc&utm_source=x&si=123")
    b = canonical_url("https://youtube.com/watch?si=999&v=abc")
    assert a == b
    assert "utm_" not in a and "si=" not in a

def test_plans_broaden_beyond_creator():
    plans = build_search_plans(
        source_platform="instagram",
        title="Dog rescued from storm drain Part 1",
        description="What happened next was incredible",
        creator="sam",
        scope="web",
    )
    labels = {p.label for p in plans}
    assert "direct continuation" in labels
    assert "full original" in labels
    assert any(p.target_platform == "youtube" for p in plans)
    assert any(p.target_platform == "tiktok" for p in plans)
    assert all(p.target_platform != "instagram" for p in plans if p.target_platform)

def test_creator_only_does_not_generate_cross_platform_plans():
    plans = build_search_plans(
        source_platform="youtube", title="Story one", description="continued later",
        creator="A", scope="creator"
    )
    assert all(p.target_platform is None for p in plans)

def test_merge_dedupes_tracking_variants():
    items = [
        cand("https://youtube.com/watch?v=abc&utm_source=x", "A", .40),
        cand("https://www.youtube.com/watch?v=abc&si=zzz", "A", .62),
    ]
    merged = merge_ranked(items)
    assert len(merged) == 1
    assert merged[0].score == .62

def test_classifies_original_and_continuation():
    original = cand("https://youtube.com/watch?v=1", "Full original source", .6, "other", "full original")
    cont = cand("https://youtube.com/watch?v=2", "Story Part 2", .6, "sam", "continuation")
    assert classify_candidate("sam", original) == "full_original"
    assert classify_candidate("sam", cont) == "official_continuation"


def test_same_creator_part2_is_official_continuation():
    from app.hunter import classify_candidate
    c = Candidate(
        title="Owl rescue Part 2",
        url="https://example.com/p2",
        platform="web",
        creator="Maya Lee",
        reason="benchmark",
        score=0.75,
    )
    assert classify_candidate("Maya Lee", c) == "official_continuation"
