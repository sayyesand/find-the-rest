import re
from .social_common import fetch_public_html, page_metadata, username_from_path
async def get_public_metadata(url: str) -> dict:
    try:
        final, doc = await fetch_public_html(url)
        data = page_metadata(doc)
        data.update({"url": final, "platform": "x", "creator": username_from_path(final)})
        return data
    except Exception:
        return {"url": url, "platform": "x"}
