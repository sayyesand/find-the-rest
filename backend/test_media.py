import subprocess
from pathlib import Path

from app.media import compare_media


def make_clip(path: Path, color: str, freq: int):
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c={color}:s=160x120:d=2:r=12",
        "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=8000:duration=2",
        "-shortest", "-c:v", "mpeg4", "-c:a", "aac", str(path)
    ], check=True)


def test_matching_media_scores_higher(tmp_path):
    source = tmp_path / "source.mp4"
    good = tmp_path / "good.mp4"
    bad = tmp_path / "bad.mp4"
    make_clip(source, "red", 440)
    make_clip(good, "red", 440)
    make_clip(bad, "blue", 880)

    good_ev = compare_media(str(source), str(good))
    bad_ev = compare_media(str(source), str(bad))

    assert good_ev.visual > bad_ev.visual
    assert good_ev.audio > bad_ev.audio
    assert good_ev.visual > 0.95
    assert good_ev.audio > 0.90
