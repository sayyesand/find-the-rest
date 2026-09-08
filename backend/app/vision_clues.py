import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
import numpy as np

from .visual import _decode_frame, _duration


@dataclass(frozen=True)
class VisualClues:
    objects: tuple[str, ...]
    logos: tuple[str, ...]
    scenes: tuple[str, ...]
    clothing: tuple[str, ...]
    local_scene_tags: tuple[str, ...]
    frames_examined: int
    provider_status: str


def _endpoint() -> str | None:
    return os.getenv("FINDREST_VISION_CLUES_ENDPOINT", "").strip() or None


def _allowed_hosts() -> set[str]:
    raw = os.getenv("FINDREST_VISION_CLUES_ALLOWED_HOSTS", "").strip()
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _validate_endpoint(endpoint: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(endpoint)
    except Exception:
        return False, "invalid_endpoint"
    if parsed.scheme != "https" or not parsed.hostname:
        return False, "https_required"
    if parsed.username or parsed.password:
        return False, "credentials_in_url_not_allowed"
    allowed = _allowed_hosts()
    if allowed and parsed.hostname.lower() not in allowed:
        return False, "host_not_allowed"
    return True, "ok"


def configured() -> bool:
    endpoint = _endpoint()
    return bool(endpoint and _validate_endpoint(endpoint)[0])


def _sample_frames(path: str, count: int = 4) -> list[np.ndarray]:
    duration = _duration(path)
    times = [0.0] if duration <= .25 else list(np.linspace(0.0, max(0.0, duration-.05), count))
    frames=[]
    for at in times:
        try:
            frame=_decode_frame(path, float(at), size=112)
        except RuntimeError:
            continue
        if float(frame.mean()) < 6 or float(frame.std()) < 4:
            continue
        frames.append(frame)
    return frames


def _local_scene_tags(frames: list[np.ndarray]) -> tuple[str, ...]:
    """Coarse, non-semantic scene tags derived locally from pixels.

    These tags do not claim object identity; they help distinguish bright/dark,
    colorful/muted, visually dense/simple, and indoor-like/outdoor-like scenes.
    """
    if not frames:
        return ()
    means=[]; sats=[]; edges=[]
    for f in frames:
        x=f.astype(np.float32)/255.0
        means.append(float(x.mean()))
        mx=x.max(axis=2); mn=x.min(axis=2)
        sats.append(float((mx-mn).mean()))
        gray=x.mean(axis=2)
        edge=float(np.abs(np.diff(gray,axis=1)).mean()+np.abs(np.diff(gray,axis=0)).mean())
        edges.append(edge)
    brightness=sum(means)/len(means)
    saturation=sum(sats)/len(sats)
    density=sum(edges)/len(edges)
    tags=[]
    tags.append("bright scene" if brightness >= .58 else "dark scene" if brightness <= .34 else "mid-tone scene")
    tags.append("colorful scene" if saturation >= .20 else "muted scene")
    tags.append("visually dense scene" if density >= .18 else "simple scene")
    return tuple(tags)


def _clean_labels(values, limit: int) -> tuple[str, ...]:
    out=[]
    seen=set()
    if not isinstance(values, list):
        return ()
    for value in values:
        text=" ".join(str(value).strip().split())[:80]
        key=text.casefold()
        if len(text) < 2 or key in seen:
            continue
        seen.add(key); out.append(text)
        if len(out) >= limit:
            break
    return tuple(out)


async def extract_visual_clues(path: str) -> VisualClues:
    frames=_sample_frames(path)
    local_tags=_local_scene_tags(frames)
    endpoint=_endpoint()
    if not endpoint:
        return VisualClues((),(),(),(),local_tags,len(frames),"provider_not_configured")
    ok,status=_validate_endpoint(endpoint)
    if not ok:
        return VisualClues((),(),(),(),local_tags,len(frames),f"provider_config_invalid_{status}")

    key=os.getenv("FINDREST_VISION_CLUES_KEY","").strip()
    headers={"Accept":"application/json"}
    if key:
        headers["Authorization"]=f"Bearer {key}"

    data=Path(path).read_bytes()
    try:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=False) as client:
            response=await client.post(
                endpoint,
                headers=headers,
                files={"media":(Path(path).name,data,"application/octet-stream")},
            )
    except Exception:
        return VisualClues((),(),(),(),local_tags,len(frames),"provider_error")

    if 300 <= response.status_code < 400:
        return VisualClues((),(),(),(),local_tags,len(frames),"provider_redirect_rejected")
    if not (200 <= response.status_code < 300):
        return VisualClues((),(),(),(),local_tags,len(frames),f"provider_http_{response.status_code}")

    ctype=(response.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype not in {"application/json","text/json"}:
        return VisualClues((),(),(),(),local_tags,len(frames),"unsupported_content_type")

    max_bytes=2*1024*1024
    try:
        max_bytes=max(65536,min(int(os.getenv("FINDREST_VISION_CLUES_MAX_RESPONSE_BYTES",str(max_bytes))),8*1024*1024))
    except ValueError:
        pass
    if len(response.content) > max_bytes:
        return VisualClues((),(),(),(),local_tags,len(frames),"response_too_large")

    try:
        payload=response.json()
    except Exception:
        return VisualClues((),(),(),(),local_tags,len(frames),"invalid_json")
    if not isinstance(payload,dict):
        return VisualClues((),(),(),(),local_tags,len(frames),"invalid_payload")

    return VisualClues(
        _clean_labels(payload.get("objects"),12),
        _clean_labels(payload.get("logos"),8),
        _clean_labels(payload.get("scenes"),8),
        _clean_labels(payload.get("clothing"),8),
        local_tags,
        len(frames),
        "ok",
    )


def clue_queries(clues: VisualClues, limit: int = 5) -> list[str]:
    candidates=[]
    if clues.logos:
        candidates.append(" ".join(clues.logos[:2]))
    if clues.objects:
        candidates.append(" ".join(clues.objects[:4]))
    if clues.scenes:
        candidates.append(" ".join(clues.scenes[:3]))
    if clues.clothing and clues.objects:
        candidates.append(" ".join(clues.clothing[:2]+clues.objects[:2]))
    if clues.logos and clues.objects:
        candidates.append(" ".join(clues.logos[:1]+clues.objects[:3]))
    seen=set(); out=[]
    for q in candidates:
        key=q.casefold()
        if q and key not in seen:
            seen.add(key); out.append(q)
    return out[:limit]


def clue_overlap(clues: VisualClues, text: str) -> tuple[float, dict[str,list[str]]]:
    hay=(text or "").casefold()
    groups={
        "objects":[x for x in clues.objects if x.casefold() in hay],
        "logos":[x for x in clues.logos if x.casefold() in hay],
        "scenes":[x for x in clues.scenes if x.casefold() in hay],
        "clothing":[x for x in clues.clothing if x.casefold() in hay],
    }
    total=sum(len(x) for x in [clues.objects,clues.logos,clues.scenes,clues.clothing])
    matched=sum(len(v) for v in groups.values())
    if total == 0:
        return 0.0, groups
    weighted=(
        len(groups["logos"])*1.4+
        len(groups["objects"])*1.0+
        len(groups["clothing"])*.9+
        len(groups["scenes"])*.7
    )
    denom=max(1.0,len(clues.logos)*1.4+len(clues.objects)+len(clues.clothing)*.9+len(clues.scenes)*.7)
    return min(1.0, weighted/denom), groups
