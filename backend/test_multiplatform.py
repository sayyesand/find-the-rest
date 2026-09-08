from app.platforms import detect_platform
from app.adapters.social_common import page_metadata, username_from_path
from app.service import _query_from_meta

def test_platform_detection():
    assert detect_platform("https://www.instagram.com/reel/abc/") == "instagram"
    assert detect_platform("https://www.facebook.com/reel/123") == "facebook"
    assert detect_platform("https://www.tiktok.com/@sam/video/123") == "tiktok"
    assert detect_platform("https://x.com/sam/status/1") == "x"
    assert detect_platform("https://www.reddit.com/r/test/comments/abc/x/") == "reddit"

def test_public_meta_parser():
    doc = """<html><head>
    <meta property="og:title" content="Rescue story — Part 1">
    <meta property="og:description" content="Wait until you see what happens next">
    <meta property="og:image" content="https://example.com/a.jpg">
    </head></html>"""
    m = page_metadata(doc)
    assert m["title"] == "Rescue story — Part 1"
    assert "happens next" in m["description"]
    assert str(m["thumbnail_url"]).endswith("a.jpg")

def test_tiktok_username():
    assert username_from_path("https://www.tiktok.com/@some.creator/video/123") == "some.creator"

def test_query_from_public_metadata():
    q = _query_from_meta({"title":"Dog rescue Part 1", "description":"Storm drain rescue continues", "creator":"Sam"})
    assert "Dog rescue" in q
    assert "Storm drain" in q
