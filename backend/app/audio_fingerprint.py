import subprocess
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AudioFingerprint:
    hashes: tuple[str, ...]
    windows: int
    duration_seconds: float


def _run(cmd: list[str]) -> bytes:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace")[-2000:])
    return proc.stdout


def _decode_audio(path: str, sample_rate: int = 8000, max_seconds: float = 90.0) -> np.ndarray:
    raw = _run([
        "ffmpeg", "-v", "error", "-i", path,
        "-t", f"{max_seconds:.2f}",
        "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-f", "s16le", "pipe:1",
    ])
    if not raw:
        return np.zeros(0, dtype=np.float32)
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    return x


def _spectral_signature(samples: np.ndarray, sample_rate: int = 8000) -> np.ndarray:
    """Compact relative spectral-energy signature, insensitive to overall volume."""
    if len(samples) < 256:
        return np.zeros(24, dtype=np.float32)
    # Remove DC and normalize RMS to reduce volume sensitivity.
    x = samples.astype(np.float32) - float(samples.mean())
    rms = float(np.sqrt(np.mean(x*x)))
    if rms > 1e-6:
        x = x / rms
    n = min(4096, len(x))
    if n < 512:
        n = len(x)
    x = x[:n] * np.hanning(n)
    mag = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(n, 1.0/sample_rate)
    # Speech/music-relevant log-ish bands, excluding sub-bass/DC.
    edges = np.geomspace(80.0, min(3600.0, sample_rate/2 - 1), 25)
    vals = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (freqs >= lo) & (freqs < hi)
        vals.append(float(np.log1p(mag[mask].sum())) if np.any(mask) else 0.0)
    v = np.array(vals, dtype=np.float32)
    v -= float(v.mean())
    std = float(v.std())
    if std > 1e-6:
        v /= std
    return v


def _bits_to_hex(bits: np.ndarray) -> str:
    flat = bits.astype(np.uint8).reshape(-1)
    pad = (-len(flat)) % 4
    if pad:
        flat = np.concatenate([flat, np.zeros(pad, dtype=np.uint8)])
    chars = []
    for i in range(0, len(flat), 4):
        val = int(flat[i])*8 + int(flat[i+1])*4 + int(flat[i+2])*2 + int(flat[i+3])
        chars.append(format(val, "x"))
    return "".join(chars)


def signature_hash(signature: np.ndarray) -> str:
    if signature.size == 0:
        return ""
    # Relative shape rather than exact amplitudes.
    d = np.diff(signature, prepend=signature[0])
    bits = np.concatenate([signature >= np.median(signature), d >= 0])
    return _bits_to_hex(bits)


def fingerprint_samples(samples: np.ndarray, sample_rate: int = 8000, window_seconds: float = 2.5) -> AudioFingerprint:
    if samples.size == 0:
        return AudioFingerprint(hashes=(), windows=0, duration_seconds=0.0)
    window = max(512, int(sample_rate * window_seconds))
    hop = max(256, window // 2)
    hashes = []
    for start in range(0, max(1, len(samples)-window+1), hop):
        chunk = samples[start:start+window]
        if len(chunk) < window//2:
            continue
        if float(np.sqrt(np.mean(chunk.astype(np.float32)**2))) < 0.002:
            continue
        h = signature_hash(_spectral_signature(chunk, sample_rate))
        if h and (not hashes or h != hashes[-1]):
            hashes.append(h)
    if not hashes and len(samples) >= 512:
        rms = float(np.sqrt(np.mean(samples.astype(np.float32)**2)))
        if rms >= 0.002:
            hashes = [signature_hash(_spectral_signature(samples, sample_rate))]
    return AudioFingerprint(
        hashes=tuple(hashes[:48]),
        windows=len(hashes[:48]),
        duration_seconds=len(samples)/sample_rate,
    )


def fingerprint_audio(path: str, sample_rate: int = 8000) -> AudioFingerprint:
    return fingerprint_samples(_decode_audio(path, sample_rate), sample_rate)


def _hash_similarity(a: str, b: str) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    bits = len(a)*4
    diff = (int(a,16) ^ int(b,16)).bit_count()
    return max(0.0, 1.0 - diff/bits)


def audio_fingerprint_similarity(a: AudioFingerprint, b: AudioFingerprint) -> tuple[float, int]:
    if not a.hashes or not b.hashes:
        return 0.0, 0
    forward = [max(_hash_similarity(x,y) for y in b.hashes) for x in a.hashes]
    reverse = [max(_hash_similarity(y,x) for x in a.hashes) for y in b.hashes]
    score = (sum(forward)/len(forward) + sum(reverse)/len(reverse))/2
    # Penalize one-window accidental matches.
    support = min(len(a.hashes), len(b.hashes))
    if support < 2:
        score *= 0.78
    return min(.99, max(0.0, score)), len(a.hashes)*len(b.hashes)
