import asyncio
import json
import numpy as np

from app.vision_clues import (
    VisualClues, _local_scene_tags, _validate_endpoint,
    clue_overlap, clue_queries, extract_visual_clues,
)


def test_local_scene_tags_are_coarse_not_object_claims():
    bright = np.full((112,112,3), 220, dtype=np.uint8)
    tags = _local_scene_tags([bright])
    assert "bright scene" in tags
    assert all(x not in tags for x in ("car", "person", "dog", "building"))


def test_visual_clue_query_priority_prefers_logos_and_objects():
    clues = VisualClues(
        objects=("fire truck","helmet","ladder"),
        logos=("FDNY",),
        scenes=("city street",),
        clothing=("turnout gear",),
        local_scene_tags=("bright scene",),
        frames_examined=2,
        provider_status="ok",
    )
    queries=clue_queries(clues)
    assert queries[0] == "FDNY"
    assert any("fire truck" in q for q in queries)


def test_visual_clue_overlap_weights_logo_and_object_matches():
    clues = VisualClues(
        objects=("fire truck","ladder"),
        logos=("FDNY",),
        scenes=("city street",),
        clothing=("turnout gear",),
        local_scene_tags=(),
        frames_examined=1,
        provider_status="ok",
    )
    score, matches = clue_overlap(clues, "FDNY fire truck response on a city street")
    assert score > .55
    assert matches["logos"] == ["FDNY"]
    assert "fire truck" in matches["objects"]


def test_visual_clue_gateway_requires_https_and_allowlist(monkeypatch):
    assert _validate_endpoint("http://example.com/vision")[0] is False
    monkeypatch.setenv("FINDREST_VISION_CLUES_ALLOWED_HOSTS","trusted.example")
    assert _validate_endpoint("https://evil.example/vision")[0] is False
    assert _validate_endpoint("https://trusted.example/vision")[0] is True


def test_visual_clue_provider_payload_is_bounded_and_cleaned(monkeypatch, tmp_path):
    media=tmp_path/"x.jpg"
    media.write_bytes(b"x")
    monkeypatch.setenv("FINDREST_VISION_CLUES_ENDPOINT","https://trusted.example/vision")
    monkeypatch.setenv("FINDREST_VISION_CLUES_ALLOWED_HOSTS","trusted.example")
    monkeypatch.setattr("app.vision_clues._sample_frames", lambda path: [])

    payload={
        "objects":["fire truck","fire truck","ladder"],
        "logos":["FDNY"],
        "scenes":["city street"],
        "clothing":["turnout gear"],
    }
    class Resp:
        status_code=200
        headers={"content-type":"application/json"}
        content=json.dumps(payload).encode()
        def json(self): return payload
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self,*a): return False
        async def post(self,*a,**k): return Resp()
    monkeypatch.setattr("app.vision_clues.httpx.AsyncClient", lambda **kwargs: Client())

    clues=asyncio.run(extract_visual_clues(str(media)))
    assert clues.provider_status == "ok"
    assert clues.objects == ("fire truck","ladder")
    assert clues.logos == ("FDNY",)
