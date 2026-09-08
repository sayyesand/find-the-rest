from pathlib import Path


def test_ios_automatic_verification_uses_ranked_candidates_endpoint():
    root = Path(__file__).resolve().parents[1]
    client = (root / "ios/FindTheRest/APIClient.swift").read_text()
    content = (root / "ios/FindTheRest/ContentView.swift").read_text()
    models = (root / "ios/FindTheRest/APIModels.swift").read_text()

    assert "verifyRankedCandidates(" in client
    assert 'v1/verify-ranked-candidates' in client
    assert "VerificationRerankResponse" in models
    assert "verificationRerank" in content
    assert "Media verification changed the leading candidate" in content
    assert "Verification-aware score:" in content


def test_backend_rerank_endpoint_is_bounded():
    root = Path(__file__).resolve().parents[1]
    main = (root / "backend/app/main.py").read_text()
    assert '@app.post("/v1/verify-ranked-candidates"' in main
    assert 'FINDREST_VERIFICATION_RERANK_MAX_CANDIDATES' in main
    assert "max(1, min(max_attempts, 3))" in main
