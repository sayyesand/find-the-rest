from urllib.parse import urlparse


def detect_platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "instagram.com" in host:
        return "instagram"
    if "facebook.com" in host or "fb.watch" in host:
        return "facebook"
    if "tiktok.com" in host:
        return "tiktok"
    if host.endswith("x.com") or "twitter.com" in host:
        return "x"
    if "reddit.com" in host:
        return "reddit"
    return "web" if host else "unknown"
