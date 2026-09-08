import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .matching import clean_text

HANDLE_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_.]{2,30})")
HASHTAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_]{2,50})")
URL_RE = re.compile(r"\b(?:https?://|www\.)[^\s<>()]+", re.I)

GENERIC = {
    "the","and","this","that","with","from","your","you","for","are","was","were",
    "have","has","had","but","not","all","can","will","just","more","what","when",
    "where","who","why","how","part","video","reel","short","follow","like","share",
}


@dataclass(frozen=True)
class VisibleTextEvidence:
    text: str
    handles: tuple[str, ...]
    hashtags: tuple[str, ...]
    urls: tuple[str, ...]
    keywords: tuple[str, ...]
    frames_examined: int
    backend: str


def _run(cmd: list[str]) -> bytes:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace")[-1600:])
    return proc.stdout


def _duration(path: str) -> float:
    try:
        out = _run([
            "ffprobe","-v","error","-show_entries","format=duration",
            "-of","default=noprint_wrappers=1:nokey=1",path,
        ]).decode().strip()
        return max(0.0, float(out))
    except Exception:
        return 0.0


def _extract_png(path: str, dest: Path, at: float | None = None) -> None:
    cmd = ["ffmpeg","-v","error"]
    if at is not None and at > 0:
        cmd += ["-ss",f"{at:.3f}"]
    cmd += ["-i",path,"-frames:v","1","-vf","scale='min(1600,iw)':-2",str(dest),"-y"]
    _run(cmd)


def _ocr_image(path: Path) -> str:
    if not shutil_which("tesseract"):
        return ""
    proc = subprocess.run(
        ["tesseract", str(path), "stdout", "--psm", "11", "-l", "eng"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.decode("utf-8", errors="replace").strip()


def shutil_which(name: str) -> str | None:
    from shutil import which
    return which(name)


def _dedupe_lines(texts: list[str]) -> str:
    seen = set()
    lines = []
    for text in texts:
        for line in text.splitlines():
            line = " ".join(line.split()).strip()
            key = clean_text(line)
            if len(key) < 2 or key in seen:
                continue
            seen.add(key)
            lines.append(line)
    return "\n".join(lines)


def _keywords(text: str, limit: int = 14) -> tuple[str, ...]:
    words = [w for w in clean_text(text).split() if len(w) >= 4 and w not in GENERIC]
    counts: dict[str, int] = {}
    order: list[str] = []
    for word in words:
        if word not in counts:
            order.append(word)
            counts[word] = 0
        counts[word] += 1
    ranked = sorted(order, key=lambda w: (-counts[w], order.index(w)))
    return tuple(ranked[:limit])


def extract_visible_text(path: str, *, max_video_frames: int = 5) -> VisibleTextEvidence:
    if not shutil_which("tesseract"):
        return VisibleTextEvidence("", (), (), (), (), 0, "tesseract_unavailable")

    ext = Path(path).suffix.lower()
    image_exts = {".jpg",".jpeg",".png",".webp",".heic",".heif",".bmp"}
    texts: list[str] = []
    frames = 0

    with tempfile.TemporaryDirectory(prefix="findrest-ocr-") as td:
        tmp = Path(td)
        if ext in image_exts:
            png = tmp/"frame-0.png"
            _extract_png(path, png)
            texts.append(_ocr_image(png))
            frames = 1
        else:
            duration = _duration(path)
            if duration <= 0.2:
                png = tmp/"frame-0.png"
                _extract_png(path, png)
                texts.append(_ocr_image(png))
                frames = 1
            else:
                count = max(1, min(max_video_frames, 5))
                if count == 1:
                    times = [0.0]
                else:
                    times = [duration * i / (count - 1) for i in range(count)]
                for i, at in enumerate(times):
                    png = tmp/f"frame-{i}.png"
                    try:
                        _extract_png(path, png, at)
                    except RuntimeError:
                        continue
                    text = _ocr_image(png)
                    texts.append(text)
                    frames += 1

    combined = _dedupe_lines(texts)
    handles = tuple(dict.fromkeys("@" + x for x in HANDLE_RE.findall(combined)))
    hashtags = tuple(dict.fromkeys("#" + x for x in HASHTAG_RE.findall(combined)))
    urls = tuple(dict.fromkeys(URL_RE.findall(combined)))
    return VisibleTextEvidence(
        text=combined,
        handles=handles,
        hashtags=hashtags,
        urls=urls,
        keywords=_keywords(combined),
        frames_examined=frames,
        backend="tesseract:eng",
    )


def visible_text_queries(ev: VisibleTextEvidence, *, limit: int = 5) -> list[str]:
    out: list[str] = []
    if ev.handles:
        out.append(" ".join(ev.handles[:2]))
    if ev.urls:
        out.append(ev.urls[0])
    if ev.hashtags:
        out.append(" ".join(ev.hashtags[:3]))
    if len(ev.keywords) >= 3:
        out.append(" ".join(ev.keywords[:5]))
    lines = [x.strip() for x in ev.text.splitlines() if len(x.strip().split()) >= 4]
    if lines:
        out.append(f'"{lines[0][:120]}"')
    seen=set(); unique=[]
    for q in out:
        if q and q not in seen:
            seen.add(q); unique.append(q)
    return unique[:limit]
