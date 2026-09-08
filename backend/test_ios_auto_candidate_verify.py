from pathlib import Path

def test_ios_automatic_candidate_verification_is_wired():
    root = Path(__file__).resolve().parents[1]
    content = (root / "ios/FindTheRest/ContentView.swift").read_text()
    client = (root / "ios/FindTheRest/APIClient.swift").read_text()
    models = (root / "ios/FindTheRest/APIModels.swift").read_text()
    main = (root / "backend/app/main.py").read_text()

    assert "attemptAutomaticVerification" in content
    assert "candidateMediaVerification" in content
    assert "verifyCandidateURL" in client
    assert "v1/verify-candidate-url" in client
    assert "struct CandidateURLVerifyResponse" in models
    assert '@app.post("/v1/verify-candidate-url"' in main
    assert "fetch_permitted_candidate_media" in main


def test_backend_does_not_directly_download_candidate_url():
    root = Path(__file__).resolve().parents[1]
    main = (root / "backend/app/main.py").read_text()
    start = main.index('@app.post("/v1/verify-candidate-url"')
    end = main.index('@app.post("/v1/verify-media-pair"', start)
    block = main[start:end]
    assert "fetch_permitted_candidate_media(candidate_url" in block
    assert "httpx" not in block
