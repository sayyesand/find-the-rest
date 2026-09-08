import os
import re
import httpx
from urllib.parse import urlparse, parse_qs
from ..models import Candidate
from ..matching import Evidence, continuation_signal, creator_similarity, sequence_signal, text_similarity

API = "https://www.googleapis.com/youtube/v3"

DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)

def iso8601_duration_seconds(value: str | None) -> float | None:
    if not value:
        return None
    m = DURATION_RE.match(value)
    if not m:
        return None
    days = float(m.group("days") or 0)
    hours = float(m.group("hours") or 0)
    minutes = float(m.group("minutes") or 0)
    seconds = float(m.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds



def extract_video_id(url: str) -> str | None:
    p = urlparse(url)
    if p.hostname in {"youtu.be", "www.youtu.be"}:
        return p.path.strip("/") or None
    if "youtube.com" in (p.hostname or ""):
        if p.path.startswith("/shorts/"):
            bits = p.path.split("/")
            return bits[2] if len(bits) > 2 else None
        if p.path.startswith("/watch"):
            return parse_qs(p.query).get("v", [None])[0]
    return None


def normalize_terms(title: str, description: str) -> str:
    text = f"{title} {description}".lower()
    text = re.sub(r"\b(part|pt)\.?\s*\d+\b", "", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    words = [w for w in text.split() if len(w) > 2]
    return " ".join(words[:12])


async def get_video_metadata(video_id: str) -> dict | None:
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        return None
    params = {"part": "snippet,contentDetails", "id": video_id, "key": key}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{API}/videos", params=params)
        r.raise_for_status()
        items = r.json().get("items", [])
        return items[0] if items else None


async def search_candidates(
    query: str,
    *,
    source_title: str,
    source_description: str,
    source_creator: str | None,
    source_published_at: str | None,
    channel_id: str | None = None,
    limit: int = 10,
) -> list[Candidate]:
    key = os.getenv("YOUTUBE_API_KEY")
    if not key or not query:
        return []
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": min(limit, 25),
        "safeSearch": "moderate",
        "key": key,
        "order": "relevance",
    }
    if channel_id:
        params["channelId"] = channel_id
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{API}/search", params=params)
        r.raise_for_status()
        data = r.json().get("items", [])

        ids = [item.get("id", {}).get("videoId") for item in data]
        ids = [v for v in ids if v]
        details_by_id = {}
        if ids:
            dparams = {"part": "contentDetails", "id": ",".join(ids), "key": key}
            dr = await client.get(f"{API}/videos", params=dparams)
            dr.raise_for_status()
            details_by_id = {x.get("id"): x.get("contentDetails", {}) for x in dr.json().get("items", [])}

    out: list[Candidate] = []
    for item in data:
        vid = item.get("id", {}).get("videoId")
        snip = item.get("snippet", {})
        if not vid:
            continue
        title = snip.get("title", "Untitled")
        desc = snip.get("description", "")
        creator = snip.get("channelTitle")
        published = snip.get("publishedAt")
        duration_seconds = iso8601_duration_seconds(details_by_id.get(vid, {}).get("duration"))
        ev = Evidence(
            text=text_similarity(source_title, source_description, title, desc),
            continuation=continuation_signal(title, desc),
            creator=creator_similarity(source_creator, creator),
            sequence=sequence_signal(source_published_at, published),
        )
        score = ev.score
        thumbs = snip.get("thumbnails", {})
        thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
        reasons = []
        if ev.continuation >= 0.7: reasons.append("explicit continuation wording")
        if ev.creator >= 0.95: reasons.append("same creator")
        if ev.sequence >= 0.5: reasons.append("posted after the source")
        if ev.text >= 0.35: reasons.append("topic/text similarity")
        reason = ", ".join(reasons) if reasons else "weak metadata similarity"
        out.append(Candidate(
            title=title,
            url=f"https://www.youtube.com/watch?v={vid}",
            platform="youtube",
            creator=creator,
            published_at=published,
            thumbnail_url=thumb,
            reason=reason.capitalize() + ".",
            snippet=desc[:600] or None,
            score=score,
            evidence=ev.as_dict(),
            duration_seconds=duration_seconds,
        ))
    return sorted(out, key=lambda c: c.score, reverse=True)
