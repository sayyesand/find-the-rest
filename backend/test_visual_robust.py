import numpy as np
from app.visual import robust_frame_similarity

def scene():
    x = np.zeros((96,96,3), dtype=np.uint8)
    x[18:78, 25:70, 0] = 220
    x[30:65, 38:82, 1] = 150
    x[45:72, 12:36, 2] = 240
    return x

def test_robust_similarity_handles_horizontal_mirror():
    a = scene()
    b = np.ascontiguousarray(a[:, ::-1])
    assert robust_frame_similarity(a,b) > .90

def test_robust_similarity_handles_caption_overlay():
    a = scene()
    b = a.copy()
    b[:15,:,:] = 255
    b[82:,:,:] = 255
    assert robust_frame_similarity(a,b) > .75

def test_robust_similarity_rejects_unrelated_geometry():
    a = scene()
    b = np.zeros((96,96,3), dtype=np.uint8)
    rng = np.random.default_rng(7)
    b[:] = rng.integers(0,256,size=b.shape,dtype=np.uint8)
    assert robust_frame_similarity(a,b) < .80
