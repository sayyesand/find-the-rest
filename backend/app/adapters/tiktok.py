import re
from .social_common import fetch_public_html, page_metadata, username_from_path
async def get_public_metadata(url: str) -> dict:
    try:
        final, doc = await fetch_public_html(url)
        data = page_metadata(doc)
        creator = username_from_path(final)
        if not creator:
            m = re.search(r'@([A-Za-z0-9._-]+)', data.get("title") or "")
            creator = m.group(1) if m else None
        data.update({"url": final, "platform": "tiktok", "creator": creator})
        return data
    except Exception:
        return {"url": url, "platform": "tiktok"}
