from app.matching import Evidence, continuation_signal, creator_similarity, sequence_signal, text_similarity


def test_continuation_wording():
    assert continuation_signal("Story Part 2", "") == 1.0
    assert continuation_signal("The update", "continued here") >= 0.7


def test_creator_similarity():
    assert creator_similarity("Creator Name", "Creator Name") == 1.0
    assert creator_similarity(None, "Creator Name") == 0.0


def test_sequence_rewards_later_posts():
    assert sequence_signal("2026-01-01T10:00:00Z", "2026-01-01T12:00:00Z") > 0.9
    assert sequence_signal("2026-01-02T10:00:00Z", "2026-01-01T12:00:00Z") == 0.0


def test_similar_text_scores_higher():
    source = ("Bear walks into grocery store", "Security camera footage from downtown")
    good = text_similarity(*source, "Bear enters grocery store part 2", "More security camera footage downtown")
    bad = text_similarity(*source, "Cake recipe", "Chocolate frosting tutorial")
    assert good > bad


def test_metadata_confidence_is_capped():
    ev = Evidence(text=1, continuation=1, creator=1, sequence=1)
    assert ev.score == 0.84


def test_content_evidence_can_raise_confidence():
    ev = Evidence(text=1, continuation=1, creator=1, sequence=1, visual=1, audio=1)
    assert ev.score > 0.9
