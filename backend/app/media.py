import math
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class MediaEvidence:
    visual: float
    audio: float
    visual_frames: int
    audio_samples: int


def _run(cmd: list[str]) -> bytes:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace")[-2000:])
    return proc.stdout


def _duration(path: str) -> float:
    out = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ]).decode().strip()
    try:
        return max(0.0, float(out))
    except ValueError:
        return 0.0


def _gray_frames(path: str, *, tail: bool, seconds: float = 2.0, fps: int = 3, size: int = 48) -> np.ndarray:
    dur = _duration(path)
    start = max(0.0, dur - seconds) if tail else 0.0
    raw = _run([
        "ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", path,
        "-t", f"{seconds:.3f}", "-vf", f"fps={fps},scale={size}:{size},format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
    ])
    frame_size = size * size
    usable = len(raw) // frame_size * frame_size
    if usable == 0:
        return np.empty((0, size, size), dtype=np.uint8)
    return np.frombuffer(raw[:usable], dtype=np.uint8).reshape((-1, size, size))


def _frame_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    # Compare several end/start frame pairs and keep the strongest plausible seam.
    pairs = []
    for fa in a[-3:]:
        for fb in b[:3]:
            mae = np.mean(np.abs(fa.astype(np.float32) - fb.astype(np.float32))) / 255.0
            pairs.append(max(0.0, 1.0 - float(mae)))
    return max(pairs, default=0.0)


def _pcm(path: str, *, tail: bool, seconds: float = 2.0, sample_rate: int = 8000) -> np.ndarray:
    dur = _duration(path)
    start = max(0.0, dur - seconds) if tail else 0.0
    raw = _run([
        "ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", path,
        "-t", f"{seconds:.3f}", "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1",
    ])
    if not raw:
        return np.empty((0,), dtype=np.float32)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32)


def _audio_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 256 or len(b) < 256:
        return 0.0
    n = min(len(a), len(b), 8000)
    a = a[-n:]
    b = b[:n]
    a = a - float(a.mean())
    b = b - float(b.mean())
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 1e-9:
        return 0.0
    corr = float(np.dot(a, b) / denom)
    # Negative phase still indicates the same periodic/audio structure at a seam.
    return max(0.0, min(1.0, abs(corr)))


def compare_media(source_path: str, candidate_path: str) -> MediaEvidence:
    sf = _gray_frames(source_path, tail=True)
    cf = _gray_frames(candidate_path, tail=False)
    sa = _pcm(source_path, tail=True)
    ca = _pcm(candidate_path, tail=False)
    return MediaEvidence(
        visual=_frame_similarity(sf, cf),
        audio=_audio_similarity(sa, ca),
        visual_frames=int(len(sf) + len(cf)),
        audio_samples=int(min(len(sa), len(ca))),
    )
