import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class FrameFingerprint:
    ahash: str
    dhash: str
    color_hist: list[float]
    edge_energy: float


@dataclass(frozen=True)
class VisualFingerprint:
    kind: str
    frames: list[FrameFingerprint]
    representative_count: int


def _run(cmd: list[str]) -> bytes:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace")[-2000:])
    return proc.stdout


def _duration(path: str) -> float:
    try:
        out = _run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ]).decode().strip()
        return max(0.0, float(out))
    except Exception:
        return 0.0


def _decode_frame(path: str, at: float = 0.0, size: int = 96) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error"]
    if at > 0:
        cmd += ["-ss", f"{at:.3f}"]
    cmd += [
        "-i", path, "-frames:v", "1",
        "-vf", f"scale={size}:{size}:force_original_aspect_ratio=decrease,"
               f"pad={size}:{size}:(ow-iw)/2:(oh-ih)/2,format=rgb24",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]
    raw = _run(cmd)
    expected = size * size * 3
    if len(raw) < expected:
        raise RuntimeError("Could not decode a visual frame")
    return np.frombuffer(raw[:expected], dtype=np.uint8).reshape((size, size, 3))


def _resize_gray(gray: np.ndarray, h: int, w: int) -> np.ndarray:
    ys = np.linspace(0, gray.shape[0] - 1, h).astype(int)
    xs = np.linspace(0, gray.shape[1] - 1, w).astype(int)
    return gray[np.ix_(ys, xs)]


def _bits_to_hex(bits: np.ndarray) -> str:
    flat = bits.astype(np.uint8).reshape(-1)
    pad = (-len(flat)) % 4
    if pad:
        flat = np.concatenate([flat, np.zeros(pad, dtype=np.uint8)])
    out = []
    for i in range(0, len(flat), 4):
        value = int(flat[i]) * 8 + int(flat[i+1]) * 4 + int(flat[i+2]) * 2 + int(flat[i+3])
        out.append(format(value, "x"))
    return "".join(out)


def fingerprint_frame(frame: np.ndarray) -> FrameFingerprint:
    x = frame.astype(np.float32) / 255.0
    gray = x.mean(axis=2)

    small = _resize_gray(gray, 8, 8)
    ahash = _bits_to_hex(small >= float(small.mean()))

    dsmall = _resize_gray(gray, 8, 9)
    dhash = _bits_to_hex(dsmall[:, 1:] >= dsmall[:, :-1])

    hist = []
    for channel in range(3):
        values, _ = np.histogram(x[:, :, channel], bins=8, range=(0.0, 1.0))
        values = values.astype(np.float32)
        values /= max(float(values.sum()), 1.0)
        hist.extend(float(v) for v in values)

    gx = np.abs(np.diff(gray, axis=1)).mean()
    gy = np.abs(np.diff(gray, axis=0)).mean()
    edge = float(min(1.0, (gx + gy) * 3.0))

    return FrameFingerprint(
        ahash=ahash,
        dhash=dhash,
        color_hist=[round(v, 6) for v in hist],
        edge_energy=round(edge, 6),
    )


def _hamming_hex(a: str, b: str) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    bits = len(a) * 4
    diff = (int(a, 16) ^ int(b, 16)).bit_count()
    return max(0.0, 1.0 - diff / bits)


def _hist_similarity(a: list[float], b: list[float]) -> float:
    if not a or len(a) != len(b):
        return 0.0
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / denom) if denom > 1e-9 else 0.0


def frame_similarity(a: FrameFingerprint, b: FrameFingerprint) -> float:
    ah = _hamming_hex(a.ahash, b.ahash)
    dh = _hamming_hex(a.dhash, b.dhash)
    hist = _hist_similarity(a.color_hist, b.color_hist)
    edge = max(0.0, 1.0 - abs(a.edge_energy - b.edge_energy))
    return max(0.0, min(1.0, ah * 0.35 + dh * 0.40 + hist * 0.15 + edge * 0.10))


def _is_visual_duplicate(candidate: FrameFingerprint, chosen: list[FrameFingerprint]) -> bool:
    return any(frame_similarity(candidate, existing) >= 0.94 for existing in chosen)


def fingerprint_media(path: str, *, max_frames: int = 7) -> VisualFingerprint:
    ext = Path(path).suffix.lower()
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp"}
    if ext in image_exts:
        fp = fingerprint_frame(_decode_frame(path))
        return VisualFingerprint(kind="image", frames=[fp], representative_count=1)

    duration = _duration(path)
    if duration <= 0.25:
        fp = fingerprint_frame(_decode_frame(path))
        return VisualFingerprint(kind="image", frames=[fp], representative_count=1)

    sample_count = min(max_frames * 2, 14)
    times = np.linspace(0.0, max(0.0, duration - 0.05), sample_count)
    chosen: list[FrameFingerprint] = []
    for at in times:
        try:
            frame = _decode_frame(path, float(at))
        except RuntimeError:
            continue
        # Reject almost-black/blank frames.
        if float(frame.mean()) < 8.0 or float(frame.std()) < 5.0:
            continue
        fp = fingerprint_frame(frame)
        if not _is_visual_duplicate(fp, chosen):
            chosen.append(fp)
        if len(chosen) >= max_frames:
            break

    if not chosen:
        chosen = [fingerprint_frame(_decode_frame(path, 0.0))]
    return VisualFingerprint(kind="video", frames=chosen, representative_count=len(chosen))


def visual_similarity(a: VisualFingerprint, b: VisualFingerprint) -> tuple[float, int]:
    if not a.frames or not b.frames:
        return 0.0, 0
    matches = []
    for fa in a.frames:
        best = max(frame_similarity(fa, fb) for fb in b.frames)
        matches.append(best)
    # Symmetric best-match scoring prevents one repeated frame from dominating.
    reverse = []
    for fb in b.frames:
        reverse.append(max(frame_similarity(fb, fa) for fa in a.frames))
    score = (sum(matches) / len(matches) + sum(reverse) / len(reverse)) / 2.0
    return max(0.0, min(0.99, score)), len(a.frames) * len(b.frames)


def _crop_variants(frame: np.ndarray) -> list[np.ndarray]:
    """Generate inexpensive local-region views for crop/overlay resilience."""
    h, w = frame.shape[:2]
    variants = [frame]
    # Center crops at several scales preserve the main subject when borders/captions differ.
    for frac in (0.82, 0.66):
        ch, cw = max(8, int(h * frac)), max(8, int(w * frac))
        y0, x0 = (h - ch) // 2, (w - cw) // 2
        variants.append(frame[y0:y0+ch, x0:x0+cw])
    # Remove common caption zones at top/bottom.
    cut = max(1, int(h * 0.16))
    if h - cut > 8:
        variants.append(frame[cut:, :])
        variants.append(frame[:h-cut, :])
    return variants


def robust_frame_similarity(a_frame: np.ndarray, b_frame: np.ndarray) -> float:
    """Compare normal, mirrored, center-cropped and caption-zone variants."""
    a_variants = _crop_variants(a_frame)
    b_variants = _crop_variants(b_frame)
    best = 0.0
    for av in a_variants:
        afp = fingerprint_frame(av)
        for bv in b_variants:
            for candidate in (bv, np.ascontiguousarray(bv[:, ::-1])):
                score = frame_similarity(afp, fingerprint_frame(candidate))
                best = max(best, score)
    return min(0.99, best)


def robust_media_similarity(source_path: str, candidate_path: str) -> tuple[float, int]:
    """Local comparison designed for repost transforms: crop, mirror and text overlays."""
    source_duration = _duration(source_path)
    candidate_duration = _duration(candidate_path)
    source_times = [0.0] if source_duration <= .25 else list(np.linspace(0.0, max(0.0, source_duration-.05), 4))
    candidate_times = [0.0] if candidate_duration <= .25 else list(np.linspace(0.0, max(0.0, candidate_duration-.05), 4))
    a_frames = []
    b_frames = []
    for at in source_times:
        try: a_frames.append(_decode_frame(source_path, float(at)))
        except RuntimeError: pass
    for at in candidate_times:
        try: b_frames.append(_decode_frame(candidate_path, float(at)))
        except RuntimeError: pass
    if not a_frames or not b_frames:
        return 0.0, 0
    forward = [max(robust_frame_similarity(a, b) for b in b_frames) for a in a_frames]
    reverse = [max(robust_frame_similarity(a, b) for a in a_frames) for b in b_frames]
    score = (sum(forward)/len(forward) + sum(reverse)/len(reverse)) / 2
    return min(.99, score), len(a_frames) * len(b_frames)
