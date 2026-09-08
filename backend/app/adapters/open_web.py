import os
import re
import httpx
from ..models import Candidate
from ..matching import Evidence, continuation_signal, text_similarity
from ..platforms import detect_platform

def _creator_from_result(title: str, url: str) -> str | None:
    platform = detect_platform(url)
    if platform == "tiktok":
        m = re.search(r"tiktok\.com/@([^/?]+)", url, re.I)
        return m.group(1) if m else None
    if platform == "x":
        m = re.search(r"(?:x|twitter)\.com/([^/?]+)/status/", url, re.I)
        return m.group(1) if m else None
    if platform == "instagram":
        m = re.search(r"instagram\.com/([^/?]+)/(?:reel|p)/", url, re.I)
        return m.group(1) if m else None
    # Search-engine titles often use "Title - Creator - YouTube"; leave unknown
    # rather than guessing when the platform URL itself doesn't identify creator.
    return None

async def search_open_web(
    query: str,
    source_url: str,
    *,
    source_title: str = "",
    source_description: str = "",
    reason_label: str = "cross-platform search",
) -> list[Candidate]:
    """Licensed search provider hook using Brave Search API when configured.
    Does not bypass logins, privacy settings, robots controls, or restricted galleries."""
    key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not key or not query:
        return []
    headers = {"Accept": "application/json", "X-Subscription-Token": key}
    params = {"q": query, "count": 10, "safesearch": "moderate", "search_lang": "en"}
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        r = await client.get("https://api.search.brave.com/res/v1/web/search", params=params)
        r.raise_for_status()
        results = r.json().get("web", {}).get("results", [])

    out: list[Candidate] = []
    for item in results:
        url = item.get("url")
        title = item.get("title") or "Untitled"
        desc = item.get("description") or ""
        if not url or url == source_url:
            continue
        platform = detect_platform(url)
        ev = Evidence(
            text=text_similarity(source_title, source_description, title, desc),
            continuation=continuation_signal(title, desc),
            creator=0.0,
            sequence=0.0,
        )
        score = min(0.84, ev.score)
        if score < 0.10:
            continue
        out.append(Candidate(
            title=title,
            url=url,
            platform=platform,
            creator=_creator_from_result(title, url),
            reason=reason_label,
            snippet=desc[:600] or None,
            score=score,
            evidence=ev.as_dict(),
        ))
    return sorted(out, key=lambda c: c.score, reverse=True)
