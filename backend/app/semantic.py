import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .media import _duration, _run

WORD_RE = re.compile(r"[a-z0-9']+", re.I)
SEMANTIC_STOP = {
    'the','a','an','and','or','but','if','then','this','that','these','those','to','of','in','on','at','for','from',
    'with','as','is','are','was','were','be','been','being','it','its','he','she','they','them','we','you','i','me',
    'my','your','our','their','so','just','very','really','um','uh'
}

@dataclass
class SemanticEvidence:
    transcript: float
    scene: float
    source_transcript: str | None
    candidate_transcript: str | None
    transcript_backend: str
    scene_frames: int


def _words(text: str | None) -> list[str]:
    if not text:
        return []
    return [w.lower() for w in WORD_RE.findall(text) if len(w) > 2 and w.lower() not in SEMANTIC_STOP]


def transcript_similarity(source: str | None, candidate: str | None) -> float:
    """Lightweight semantic/topic continuity score.

    Uses term-frequency cosine + phrase-sequence overlap. It is deterministic and works
    without a cloud model. When a stronger embedding provider is added later this function
    can be replaced without changing the API.
    """
    a, b = _words(source), _words(candidate)
    if not a or not b:
        return 0.0
    vocab = sorted(set(a) | set(b))
    ai = {w: i for i, w in enumerate(vocab)}
    va = np.zeros(len(vocab), dtype=np.float32)
    vb = np.zeros(len(vocab), dtype=np.float32)
    for w in a:
        va[ai[w]] += 1.0
    for w in b:
        vb[ai[w]] += 1.0
    # sublinear TF reduces domination by repeated names/words
    va[va > 0] = 1.0 + np.log(va[va > 0])
    vb[vb > 0] = 1.0 + np.log(vb[vb > 0])
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    cosine = float(np.dot(va, vb) / denom) if denom > 1e-9 else 0.0

    # Reward candidate openings that reuse the final concepts from the source ending.
    tail = a[-24:]
    head = b[:36]
    overlap = len(set(tail) & set(head)) / max(len(set(tail)), 1)
    return max(0.0, min(1.0, 0.72 * cosine + 0.28 * overlap))


def _rgb_frames(path: str, *, tail: bool, seconds: float = 4.0, fps: int = 2, size: int = 64) -> np.ndarray:
    dur = _duration(path)
    start = max(0.0, dur - seconds) if tail else 0.0
    raw = _run([
        'ffmpeg','-v','error','-ss',f'{start:.3f}','-i',path,'-t',f'{seconds:.3f}',
        '-vf',f'fps={fps},scale={size}:{size},format=rgb24','-f','rawvideo','-pix_fmt','rgb24','pipe:1'
    ])
    frame_size = size * size * 3
    usable = len(raw) // frame_size * frame_size
    if usable == 0:
        return np.empty((0,size,size,3), dtype=np.uint8)
    return np.frombuffer(raw[:usable], dtype=np.uint8).reshape((-1,size,size,3))


def _frame_embedding(frame: np.ndarray) -> np.ndarray:
    x = frame.astype(np.float32) / 255.0
    # Color histograms capture clothing/scene palette while remaining resilient to crops.
    hist_parts = []
    for c in range(3):
        hist, _ = np.histogram(x[:,:,c], bins=12, range=(0.0,1.0), density=False)
        hist_parts.append(hist.astype(np.float32) / max(float(hist.sum()),1.0))
    # Coarse spatial luminance grid captures scene layout without requiring exact seam frames.
    gray = x.mean(axis=2)
    blocks = []
    for iy in range(4):
        for ix in range(4):
            block = gray[iy*16:(iy+1)*16, ix*16:(ix+1)*16]
            blocks.append(float(block.mean()))
            blocks.append(float(block.std()))
    emb = np.concatenate(hist_parts + [np.array(blocks, dtype=np.float32)])
    norm = float(np.linalg.norm(emb))
    return emb / norm if norm > 1e-9 else emb


def _scene_embedding(frames: np.ndarray) -> np.ndarray | None:
    if len(frames) == 0:
        return None
    embs = np.stack([_frame_embedding(f) for f in frames])
    emb = embs.mean(axis=0)
    norm = float(np.linalg.norm(emb))
    return emb / norm if norm > 1e-9 else emb


def scene_similarity(source_path: str, candidate_path: str) -> tuple[float,int]:
    source = _rgb_frames(source_path, tail=True)
    candidate = _rgb_frames(candidate_path, tail=False)
    a = _scene_embedding(source)
    b = _scene_embedding(candidate)
    if a is None or b is None:
        return 0.0, int(len(source) + len(candidate))
    cosine = float(np.dot(a,b))
    # Embeddings are nonnegative; remap to emphasize meaningful closeness.
    score = max(0.0, min(1.0, (cosine - 0.35) / 0.65))
    return score, int(len(source) + len(candidate))


def transcribe_media(path: str) -> tuple[str | None, str]:
    """Optional local transcription via faster-whisper.

    Disabled unless FINDREST_LOCAL_WHISPER=1. The optional dependency/model are kept
    outside the base install because they are large. This avoids silently uploading audio.
    """
    import os
    if os.getenv('FINDREST_LOCAL_WHISPER', os.getenv('ENABLE_LOCAL_TRANSCRIPTION','0')) != '1':
        return None, 'not_enabled'
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception:
        return None, 'faster_whisper_unavailable'
    model_name = os.getenv('FINDREST_WHISPER_MODEL','tiny.en')
    model = WhisperModel(model_name, device='cpu', compute_type='int8')
    segments, _ = model.transcribe(path, vad_filter=True)
    text = ' '.join(seg.text.strip() for seg in segments if seg.text.strip()).strip()
    return text or None, f'faster_whisper:{model_name}'


def compare_semantics(
    source_path: str,
    candidate_path: str,
    source_transcript: str | None = None,
    candidate_transcript: str | None = None,
) -> SemanticEvidence:
    backend = 'provided'
    if not source_transcript:
        source_transcript, s_backend = transcribe_media(source_path)
        backend = s_backend
    if not candidate_transcript:
        candidate_transcript, c_backend = transcribe_media(candidate_path)
        if backend == 'provided':
            backend = c_backend
        elif c_backend != backend:
            backend = f'{backend}+{c_backend}'
    scene, frames = scene_similarity(source_path, candidate_path)
    return SemanticEvidence(
        transcript=transcript_similarity(source_transcript, candidate_transcript),
        scene=scene,
        source_transcript=source_transcript,
        candidate_transcript=candidate_transcript,
        transcript_backend=backend,
        scene_frames=frames,
    )
