from app.fingerprint import fingerprint_story, build_fingerprint_queries, fingerprint_overlap

def test_fingerprint_extracts_names_numbers_and_keywords():
    fp = fingerprint_story(
        "Maya finds a dog in Albuquerque",
        'She said "I heard barking under the bridge" near Route 66 in 2024.'
    )
    assert any("Maya" in x for x in fp.names)
    assert "2024" in fp.numbers
    assert "albuquerque" in fp.keywords
    assert fp.phrases

def test_queries_do_not_require_part_two_wording():
    fp = fingerprint_story(
        "Maya finds a dog in Albuquerque",
        'She said "I heard barking under the bridge" near Route 66.'
    )
    queries = build_fingerprint_queries(fp, "RescueDaily")
    assert queries
    assert any("barking under the bridge" in q for q in queries)
    assert all("part 2" not in q.lower() for q in queries)

def test_overlap_finds_same_story_with_different_title():
    fp = fingerprint_story(
        "Maya finds a dog in Albuquerque",
        'She heard barking under the bridge near Route 66.'
    )
    candidate = "Rescue update: barking under the bridge on Route 66 led Maya to the missing dog"
    score = fingerprint_overlap(fp, candidate)
    assert score >= 0.25

def test_single_generic_hit_is_not_strong():
    fp = fingerprint_story("Dog rescue story", "Someone found a dog near a bridge")
    assert fingerprint_overlap(fp, "Funny dog compilation") < 0.25
