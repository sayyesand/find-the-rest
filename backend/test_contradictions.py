from app.fingerprint import fingerprint_story
from app.contradictions import contradiction_evidence, apply_contradiction_guard

def test_conflicting_year_is_penalized():
    fp = fingerprint_story("Maya rescue in Albuquerque", "The storm drain incident happened in 2024.")
    ev = contradiction_evidence(fp, "Another rescue story from 2021 in Phoenix")
    assert ev.number_conflict == 1.0
    guarded, _ = apply_contradiction_guard(fp, "Another rescue story from 2021 in Phoenix", 0.70)
    assert guarded < 0.70

def test_conflicting_name_is_penalized():
    fp = fingerprint_story("Maya found the dog", "Maya climbed under the bridge")
    ev = contradiction_evidence(fp, "Jessica returns to the bridge to find the dog")
    assert ev.name_conflict > 0

def test_matching_anchor_avoids_missing_anchor_penalty():
    fp = fingerprint_story("Maya finds dog in Albuquerque", "Route 66 bridge rescue in 2024")
    ev = contradiction_evidence(fp, "Maya returns to Route 66 bridge in Albuquerque after the rescue")
    assert ev.missing_anchor == 0.0
    assert ev.penalty < 0.2

def test_empty_candidate_has_no_penalty():
    fp = fingerprint_story("Maya story", "bridge rescue")
    ev = contradiction_evidence(fp, "")
    assert ev.penalty == 0.0


def test_generic_number_does_not_conflict_with_candidate_year():
    fp = fingerprint_story("Route 66 rescue", "Maya searched near Route 66.")
    ev = contradiction_evidence(fp, "Maya returned in 2021 to discuss the Route 66 rescue")
    assert ev.number_conflict == 0.0
