from app.visible_text import VisibleTextEvidence, visible_text_queries, _keywords

def test_visible_text_query_prefers_handle():
    ev = VisibleTextEvidence(
        text="@maker This unusual chair was built in Albuquerque #woodwork",
        handles=("@maker",),
        hashtags=("#woodwork",),
        urls=(),
        keywords=("unusual","chair","built","albuquerque","woodwork"),
        frames_examined=1,
        backend="test",
    )
    qs = visible_text_queries(ev)
    assert qs[0] == "@maker"
    assert any("unusual" in q for q in qs)

def test_visible_text_query_uses_url():
    ev = VisibleTextEvidence(
        text="Source www.example.com/story",
        handles=(),
        hashtags=(),
        urls=("www.example.com/story",),
        keywords=("source",),
        frames_examined=1,
        backend="test",
    )
    assert "www.example.com/story" in visible_text_queries(ev)

def test_keywords_drop_generic_social_words():
    words = _keywords("Follow like share this video mysterious bridge Albuquerque rescue")
    assert "follow" not in words
    assert "video" not in words
    assert "mysterious" in words
    assert "albuquerque" in words
