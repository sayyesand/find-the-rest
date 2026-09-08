from app.ending import ending_fingerprint, build_ending_queries, ending_overlap, ending_boost

def test_cliffhanger_detected_from_tail():
    fp = ending_fingerprint(
        "Maya climbed beneath the bridge. She reached for the dog, but then she heard another voice behind her."
    )
    assert fp.cliffhanger_strength >= 0.6
    assert "voice" in fp.tail_terms

def test_ending_queries_focus_on_last_terms():
    fp = ending_fingerprint(
        "Earlier details do not matter much. At the end Maya found a red backpack beneath the bridge."
    )
    qs = build_ending_queries(fp)
    assert qs
    joined = " ".join(qs)
    assert "backpack" in joined
    assert "bridge" in joined

def test_continuation_with_tail_details_scores_higher():
    fp = ending_fingerprint(
        "Maya reached the storm drain and found a red backpack. But then she heard someone calling her name."
    )
    good = ending_boost(fp, "Maya follows the voice after finding the red backpack near the storm drain")
    weak = ending_boost(fp, "General dog rescue compilation from another city")
    assert good > weak
    assert good >= 0.25

def test_no_transcript_graceful():
    fp = ending_fingerprint(None, "")
    assert fp.tail_terms == ()
    assert ending_overlap(fp, "anything") == 0.0


def test_question_mark_ending_counts_as_cliffhanger():
    fp = ending_fingerprint("She opened the old wooden box and stared inside. What was underneath?")
    assert fp.cliffhanger_strength >= 0.72
