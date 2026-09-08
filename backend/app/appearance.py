from dataclasses import dataclass

import numpy as np

from .visual import _decode_frame, _duration, fingerprint_frame, frame_similarity


@dataclass(frozen=True)
class AppearanceComparison:
    face_region_similarity: float
    clothing_region_similarity: float
    scene_region_similarity: float
    combined_similarity: float
    frames_compared: int
    likely_same_visible_person: bool


def _regions(frame: np.ndarray) -> dict[str, np.ndarray]:
    """Return broad appearance regions without performing biometric identification.

    Frames are normalized to square before this step. The upper-center region is a
    face/head *region heuristic*, not a detected or enrolled face template.
    """
    h, w = frame.shape[:2]
    return {
        "face": frame[int(h*.08):int(h*.46), int(w*.24):int(w*.76)],
        "clothing": frame[int(h*.38):int(h*.82), int(w*.15):int(w*.85)],
        "scene": frame[int(h*.08):int(h*.92), int(w*.05):int(w*.95)],
    }


def _region_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    a_fp = fingerprint_frame(a)
    normal = frame_similarity(a_fp, fingerprint_frame(b))
    mirrored = frame_similarity(a_fp, fingerprint_frame(np.ascontiguousarray(b[:, ::-1])))
    return max(normal, mirrored)


def _sample_frames(path: str, count: int = 4) -> list[np.ndarray]:
    duration = _duration(path)
    times = [0.0] if duration <= .25 else list(np.linspace(0.0, max(0.0, duration-.05), count))
    frames = []
    for at in times:
        try:
            frame = _decode_frame(path, float(at), size=112)
        except RuntimeError:
            continue
        if float(frame.mean()) < 8 or float(frame.std()) < 5:
            continue
        frames.append(frame)
    return frames


def _symmetric_best(a: list[np.ndarray], b: list[np.ndarray], region: str) -> float:
    if not a or not b:
        return 0.0
    forward = []
    for af in a:
        ar = _regions(af)[region]
        forward.append(max(_region_similarity(ar, _regions(bf)[region]) for bf in b))
    reverse = []
    for bf in b:
        br = _regions(bf)[region]
        reverse.append(max(_region_similarity(br, _regions(af)[region]) for af in a))
    return (sum(forward)/len(forward) + sum(reverse)/len(reverse)) / 2


def compare_appearance(source_path: str, candidate_path: str) -> AppearanceComparison:
    """Pairwise, ephemeral appearance comparison for a specific search.

    This does not identify a person, assign a name, create an embedding database, or
    retain a reusable biometric profile. It compares broad visual regions only.
    """
    source = _sample_frames(source_path)
    candidate = _sample_frames(candidate_path)
    if not source or not candidate:
        return AppearanceComparison(0.0, 0.0, 0.0, 0.0, 0, False)

    face = min(.99, _symmetric_best(source, candidate, "face"))
    clothing = min(.99, _symmetric_best(source, candidate, "clothing"))
    scene = min(.99, _symmetric_best(source, candidate, "scene"))

    # Appearance is strongest when upper-body and clothing agree. Scene is useful
    # context but deliberately receives less weight so the same room alone cannot
    # imply the same visible person.
    combined = min(.99, face*.46 + clothing*.38 + scene*.16)
    likely = bool(face >= .72 and clothing >= .62 and combined >= .68)

    return AppearanceComparison(
        face_region_similarity=round(face, 4),
        clothing_region_similarity=round(clothing, 4),
        scene_region_similarity=round(scene, 4),
        combined_similarity=round(combined, 4),
        frames_compared=len(source) * len(candidate),
        likely_same_visible_person=likely,
    )
