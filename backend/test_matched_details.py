from app.fingerprint import StoryFingerprint, fingerprint_matches
from app.ending import EndingFingerprint, ending_matches
from app.models import Candidate
from app.service import _enrich_candidates


def test_fingerprint_matches_explains_exact_details():
    fp = StoryFingerprint(
        names=("Maya Torres",),
        phrases=("old bridge rescue",),
        keywords=("bridge","rescue","river"),
        numbers=("2024",),
    )
    text = "Maya Torres returns to the old bridge rescue in 2024 after the river search."
    details = fingerprint_matches(fp, text)
    assert details["names"] == ["Maya Torres"]
    assert "old bridge rescue" in details["phrases"]
    assert "2024" in details["numbers"]
    assert "bridge" in details["keywords"]


def test_ending_matches_reports_tail_terms():
    fp = EndingFingerprint("then she opened the locked cellar door", ("opened","locked","cellar","door"), .8)
    hits = ending_matches(fp, "Part 2 begins as the locked cellar door opens")
    assert "locked" in hits
    assert "cellar" in hits
    assert "door" in hits


def test_internal_reason_label_does_not_create_story_match():
    fp = StoryFingerprint((),(),("fingerprint","search"),())
    ending = EndingFingerprint("",(),0.0)
    c = Candidate(
        title="Completely unrelated cooking video",
        url="https://example.com/1",
        platform="web",
        reason="story fingerprint 1",
        snippet="A recipe for tomato soup",
        score=.2,
        evidence={},
    )
    out = _enrich_candidates([c], fp, ending)[0]
    assert out.evidence["story_fingerprint"] == 0.0
    assert out.matched_details == {}


def test_real_snippet_creates_match_even_when_reason_is_generic():
    fp = StoryFingerprint(("Maya",),(),("bridge","rescue"),())
    ending = EndingFingerprint("",(),0.0)
    c = Candidate(
        title="Update",
        url="https://example.com/2",
        platform="web",
        reason="cross-platform search",
        snippet="Maya returned to the bridge after the rescue",
        score=.2,
        evidence={},
    )
    out = _enrich_candidates([c], fp, ending)[0]
    assert out.evidence["story_fingerprint"] > 0
    assert "Maya" in out.matched_details.get("names", [])
