import os
from fastapi.testclient import TestClient

from app.main import app


def test_health_is_public(monkeypatch):
    monkeypatch.setenv("FIND_THE_REST_API_KEY", "secret")
    r = TestClient(app).get("/health")
    assert r.status_code == 200

def test_analyze_requires_key_when_configured(monkeypatch):
    monkeypatch.setenv("FIND_THE_REST_API_KEY", "secret")
    r = TestClient(app).post("/v1/analyze", json={"url":"https://example.com/video","scope":"web"})
    assert r.status_code == 401

def test_analyze_accepts_correct_key(monkeypatch):
    monkeypatch.setenv("FIND_THE_REST_API_KEY", "secret")
    r = TestClient(app).post("/v1/analyze", headers={"X-FindTheRest-Key":"secret"}, json={"url":"https://example.com/video","scope":"web"})
    assert r.status_code != 401
