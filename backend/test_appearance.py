import numpy as np

from app.appearance import _regions, _region_similarity, compare_appearance


def frame(face=(180,120,90), clothing=(40,90,180), scene=(80,80,80)):
    x = np.zeros((112,112,3), dtype=np.uint8)
    x[:] = scene
    x[10:52, 28:84] = face
    x[44:92, 18:94] = clothing
    return x


def test_region_similarity_is_mirror_tolerant():
    a = frame()
    b = np.ascontiguousarray(a[:, ::-1])
    ar = _regions(a)["face"]
    br = _regions(b)["face"]
    assert _region_similarity(ar, br) > .90


def test_clothing_change_reduces_clothing_similarity():
    a = frame(clothing=(30,60,190))
    b = frame(clothing=(190,40,30))
    same = _region_similarity(_regions(a)["clothing"], _regions(a)["clothing"])
    changed = _region_similarity(_regions(a)["clothing"], _regions(b)["clothing"])
    assert same > changed
    assert same > .95


def test_compare_appearance_is_pairwise_and_ephemeral(monkeypatch):
    a = frame()
    b = frame()
    monkeypatch.setattr("app.appearance._sample_frames", lambda path, count=4: [a, b])
    result = compare_appearance("source.mp4", "candidate.mp4")
    assert result.frames_compared == 4
    assert result.combined_similarity > .85
    assert result.likely_same_visible_person is True


def test_scene_alone_cannot_imply_same_visible_person(monkeypatch):
    source = frame(face=(220,220,220), clothing=(10,10,10), scene=(70,70,70))
    candidate = frame(face=(20,20,20), clothing=(240,240,240), scene=(70,70,70))
    monkeypatch.setattr(
        "app.appearance._sample_frames",
        lambda path, count=4: [source] if "source" in path else [candidate],
    )
    result = compare_appearance("source.mp4", "candidate.mp4")
    assert result.scene_region_similarity > result.clothing_region_similarity
    assert result.likely_same_visible_person is False
