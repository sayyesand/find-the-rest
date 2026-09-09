from pathlib import Path


WEB = Path(__file__).parent / "web"


def test_social_no_match_handoff_is_wired():
    html = (WEB / "index.html").read_text()
    js = (WEB / "app.js").read_text()

    assert 'id="social-search-fallback"' in html
    assert 'id="social-search-link"' in html
    assert "publicSocialSearchURL" in js
    assert "site:${domain}" in js
    assert "nextPartPhrase" in js


def test_web_assets_are_cache_busted_for_iphone_home_screen():
    html = (WEB / "index.html").read_text()

    assert "/assets/app.js?v=social-search-2" in html
    assert "/assets/styles.css?v=social-search-2" in html
