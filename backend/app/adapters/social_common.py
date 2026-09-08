import html
import re
from urllib.parse import urlparse
import httpx

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"

def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()

async def fetch_public_html(url: str, *, max_bytes: int = 1_500_000) -> tuple[str, str]:
    """Fetch only an ordinary public page. No login bypass, private content, or gallery crawling."""
    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers={"User-Agent": UA}) as client:
        r = await client.get(url)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if "text/html" not in ctype and "application/xhtml" not in ctype:
            return str(r.url), ""
        body = r.content[:max_bytes].decode(r.encoding or "utf-8", errors="ignore")
        return str(r.url), body

def meta_value(doc: str, key: str) -> str | None:
    # Handles property/name before or after content.
    pats = [
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']*)',
        rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
    ]
    for p in pats:
        m = re.search(p, doc, flags=re.I)
        if m:
            return clean_text(m.group(1))
    return None

def page_metadata(doc: str) -> dict:
    title = meta_value(doc, "og:title") or meta_value(doc, "twitter:title")
    desc = meta_value(doc, "og:description") or meta_value(doc, "twitter:description") or meta_value(doc, "description")
    image = meta_value(doc, "og:image") or meta_value(doc, "twitter:image")
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", doc, flags=re.I | re.S)
        title = clean_text(m.group(1)) if m else None
    return {"title": title, "description": desc, "thumbnail_url": image}

def username_from_path(url: str) -> str | None:
    bits = [x for x in urlparse(url).path.split("/") if x]
    if not bits:
        return None
    first = bits[0].lstrip("@")
    reserved = {"reel","reels","p","watch","video","videos","shorts","status"}
    return None if first.lower() in reserved else first
