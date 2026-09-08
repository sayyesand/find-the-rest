from app.matching import Evidence, continuation_signal, creator_similarity, sequence_signal, text_similarity

SOURCE = {
    "id": "239",
    "title": "239 - Mahabharata - Draupadi",
    "description": "A story from the Mahabharata about Draupadi's birth and her Swayamvar, featuring recipes for revenge served cold, and an insanely difficult archery contest. Previous Mahabharata episodes. Pandavas Arjun Bhima Duryodhan Karna Drupad Swayamvar.",
    "creator": "Stories From India",
    "published": "2024-01-14T00:00:00Z",
}

# Candidate set contains all eight intervening releases plus the real continuation.
# The expected ID is used only after ranking, never as a feature.
CANDIDATES = [
    {"id":"240","title":"240 - History - Tipu Sultan","description":"A story from History about Tipu Sultan, the Tiger of Mysore and the Anglo-Mysore wars.","published":"2024-01-21T00:00:00Z"},
    {"id":"241","title":"241 - Singhasan Battisi - Corpse Bride","description":"A Singhasan Battisi story featuring Raja Vikramaditya and Raja Bhoja.","published":"2024-01-28T00:00:00Z"},
    {"id":"242","title":"242 - Uttar Pradesh Folk Tale - The Lion's Wedding","description":"An Uttar Pradesh folk tale about a misunderstood lion and his upcoming wedding.","published":"2024-02-04T00:00:00Z"},
    {"id":"243","title":"243 - Saptarishi - Diti and Kashyap","description":"A story about Kashyap, Diti and Aditi and powerful Asuras.","published":"2024-02-11T00:00:00Z"},
    {"id":"244","title":"244 - Kathasaritasagara - An unfinished story","description":"A Kathasaritasagara story.","published":"2024-02-18T00:00:00Z"},
    {"id":"245","title":"245 - Ramayana - Laxman vs Indrajit","description":"A Ramayana battle involving Laxman and Indrajit.","published":"2024-02-25T00:00:00Z"},
    {"id":"246","title":"246 - History - Madhvacharya and Kanakadasa","description":"A history story about Madhvacharya and Kanakadasa.","published":"2024-03-03T00:00:00Z"},
    {"id":"247","title":"247 - Tenali-Raman - Raman vs Animals","description":"Two Tenali Raman stories featuring a parrot and a camel.","published":"2024-03-10T00:00:00Z"},
    {"id":"248","title":"248 - Mahabharata - Draupadi weds the Pandavas","description":"The Mahabharata continued, with an explanation of how Draupadi ended up marrying all 5 Pandavas. Also murderous plots, arson accusations and insurance fraud. Previous Mahabharata episodes. Krishna Arjun Draupadi Pandavas Drupad.","published":"2024-03-17T00:00:00Z"},
]


def rank_candidates():
    ranked = []
    for c in CANDIDATES:
        ev = Evidence(
            text=text_similarity(SOURCE["title"], SOURCE["description"], c["title"], c["description"]),
            continuation=continuation_signal(c["title"], c["description"]),
            creator=creator_similarity(SOURCE["creator"], "Stories From India"),
            sequence=sequence_signal(SOURCE["published"], c["published"]),
        )
        ranked.append((c["id"], ev.score, ev))
    return sorted(ranked, key=lambda x: x[1], reverse=True)


def test_draupadi_hidden_continuation_ranks_first():
    ranked = rank_candidates()
    assert ranked[0][0] == "248", [(i, round(s, 4)) for i, s, _ in ranked]


def test_draupadi_match_clears_production_threshold():
    from app.service import MIN_MATCH_CONFIDENCE
    ranked = rank_candidates()
    assert ranked[0][1] >= MIN_MATCH_CONFIDENCE
