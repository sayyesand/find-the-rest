from .platforms import detect_platform
from .adapters import instagram, facebook, tiktok, x, reddit, generic_web

ADAPTERS = {
    "instagram": instagram,
    "facebook": facebook,
    "tiktok": tiktok,
    "x": x,
    "reddit": reddit,
    "web": generic_web,
}

async def public_metadata(url: str) -> dict:
    platform = detect_platform(url)
    adapter = ADAPTERS.get(platform)
    if not adapter:
        return {"url": url, "platform": platform}
    return await adapter.get_public_metadata(url)
