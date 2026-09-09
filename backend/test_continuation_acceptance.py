from app.matching import credible_continuation
from app.models import Candidate


def candidate(title, creator, evidence=None):
    return Candidate(
        title=title,
        url="https://youtube.com/watch?v=test",
        platform="youtube",
        creator=creator,
        reason="fixture",
        score=.75,
        evidence=evidence or {},
    )


def test_rejects_different_song_from_same_creator():
    result = candidate(
        "Rick Astley - Whenever You Need Somebody (Official Video) (4K Remaster)",
        "Rick Astley",
        {"continuation_signal": 1.0, "creator_match": 1.0, "sequence_signal": .8},
    )
    assert not credible_continuation(
        source_title="Rick Astley - Never Gonna Give You Up (Official Music Video)",
        source_creator="Rick Astley",
        candidate=result,
    )


def test_accepts_numbered_follow_up_with_shared_story_topic():
    result = candidate(
        "Garuda: The War With Gods (Part 2)",
        "THE 150 TALES",
        {"continuation_signal": 1.0, "creator_match": 1.0},
    )
    assert credible_continuation(
        source_title="Garuda: The Wings Of Fire (Part 1)",
        source_creator="THE 150 TALES",
        candidate=result,
    )
