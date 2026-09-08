import subprocess
from pathlib import Path

from app.semantic import transcript_similarity, scene_similarity
from app.matching import Evidence


def make_clip(path: Path, color: str):
    subprocess.run([
        'ffmpeg','-y','-v','error',
        '-f','lavfi','-i',f'color=c={color}:s=160x120:d=2:r=12',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=8000:duration=2',
        '-shortest','-c:v','mpeg4','-c:a','aac',str(path)
    ], check=True)


def test_transcript_continuation_beats_unrelated():
    source = 'I followed the dog into the abandoned warehouse and discovered a locked blue door behind the stairs.'
    good = 'Behind the blue door, the dog stopped barking and I finally saw what had been hidden in the warehouse.'
    bad = 'Today we are making pancakes with fresh berries and maple syrup for breakfast.'
    assert transcript_similarity(source, good) > transcript_similarity(source, bad)
    assert transcript_similarity(source, good) > 0.20


def test_scene_embedding_same_setting_beats_different(tmp_path):
    a = tmp_path/'a.mp4'; good = tmp_path/'good.mp4'; bad = tmp_path/'bad.mp4'
    make_clip(a, 'red'); make_clip(good, 'red'); make_clip(bad, 'blue')
    same, _ = scene_similarity(str(a), str(good))
    diff, _ = scene_similarity(str(a), str(bad))
    assert same > diff
    assert same > 0.90


def test_semantics_raise_rank_when_boundary_is_edited():
    base = Evidence(text=.45, continuation=.2, creator=1.0, sequence=.6)
    semantic = Evidence(text=.45, continuation=.2, creator=1.0, sequence=.6, transcript=.85, scene=.80)
    assert semantic.score > base.score
    assert semantic.as_dict()['transcript_semantic'] == .85
