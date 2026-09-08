from .social_common import fetch_public_html, page_metadata
async def get_public_metadata(url: str) -> dict:
    try:
        final, doc = await fetch_public_html(url)
        data = page_metadata(doc)
        data.update({"url": final, "platform": "facebook"})
        return data
    except Exception:
        return {"url": url, "platform": "facebook"}
