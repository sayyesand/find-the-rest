import numpy as np

from app.visual import fingerprint_frame, frame_similarity, VisualFingerprint, visual_similarity


def solid_with_square(bg: int, fg: int, shift: int = 0):
    img = np.full((96,96,3), bg, dtype=np.uint8)
    img[24:72, 24+shift:72+shift, :] = fg
    return img


def test_identical_frame_is_near_one():
    a = fingerprint_frame(solid_with_square(20, 220))
    assert frame_similarity(a, a) > 0.99


def test_modest_brightness_change_stays_similar():
    a = fingerprint_frame(solid_with_square(20, 220))
    b = fingerprint_frame(solid_with_square(35, 235))
    assert frame_similarity(a, b) > 0.80


def test_different_layout_scores_lower():
    a = fingerprint_frame(solid_with_square(20, 220))
    b_img = np.full((96,96,3), 20, dtype=np.uint8)
    b_img[5:28, 5:90, :] = 220
    b = fingerprint_frame(b_img)
    assert frame_similarity(a, b) < frame_similarity(a, a)


def test_visual_similarity_uses_representative_frames():
    a1 = fingerprint_frame(solid_with_square(20, 220))
    a2 = fingerprint_frame(solid_with_square(30, 180, shift=5))
    b1 = fingerprint_frame(solid_with_square(25, 225))
    b2 = fingerprint_frame(solid_with_square(35, 185, shift=5))
    va = VisualFingerprint("video", [a1,a2], 2)
    vb = VisualFingerprint("video", [b1,b2], 2)
    score, pairs = visual_similarity(va, vb)
    assert score > 0.75
    assert pairs == 4
