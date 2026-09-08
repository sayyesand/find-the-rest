import os
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get('/health')
    assert r.status_code == 200
    assert r.json()['ok'] is True

def test_accepts_instagram_url_without_scraping():
    r = client.post('/v1/analyze', json={'url':'https://www.instagram.com/reel/example','scope':'web'})
    assert r.status_code == 200
    body = r.json()
    assert body['source_platform'] == 'instagram'
    assert body['match_type'] == 'no_match'
