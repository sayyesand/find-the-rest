from pathlib import Path

from app.beta_readiness import readiness_summary


def test_public_health_does_not_expose_cache_internals():
    root=Path(__file__).resolve().parents[1]
    main=(root/"backend/app/main.py").read_text()
    start=main.index('@app.get("/health")')
    block=main[start:start+500]
    assert '"cache": cache_stats()' not in block
    assert '"version"' in block


def test_cors_is_not_wildcard_by_default():
    root=Path(__file__).resolve().parents[1]
    main=(root/"backend/app/main.py").read_text()
    assert 'allow_origins=["*"]' not in main
    assert 'FINDREST_CORS_ORIGINS' in main
    assert 'FINDREST_TRUSTED_HOSTS' in main


def test_readiness_reports_http_boundary_gates(monkeypatch):
    monkeypatch.setenv("FIND_THE_REST_API_KEY","this-is-a-strong-beta-key")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY","configured")
    monkeypatch.delenv("FINDREST_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("FINDREST_TRUSTED_HOSTS", raising=False)
    gates={g["gate_id"]:g for g in readiness_summary()["gates"]}
    assert gates["cors-policy"]["passed"] is True
    assert gates["trusted-hosts"]["passed"] is False
    assert gates["trusted-hosts"]["critical"] is False


def test_wildcard_cors_is_flagged(monkeypatch):
    monkeypatch.setenv("FINDREST_CORS_ORIGINS","*")
    gates={g["gate_id"]:g for g in readiness_summary()["gates"]}
    assert gates["cors-policy"]["passed"] is False


def test_ios_release_check_and_readable_errors_are_wired():
    root=Path(__file__).resolve().parents[1]
    client=(root/"ios/FindTheRest/APIClient.swift").read_text()
    models=(root/"ios/FindTheRest/APIModels.swift").read_text()
    content=(root/"ios/FindTheRest/ContentView.swift").read_text()
    assert "func betaReadiness()" in client
    assert "BetaReadinessResponse" in models
    assert 'Section("Release readiness")' in content
    assert '"Run Release Check"' in content
    assert "BackendServiceError.authentication" in client
    assert "request.timeoutInterval = 12" in client
