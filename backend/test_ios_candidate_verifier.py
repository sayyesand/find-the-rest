from pathlib import Path

def test_ios_candidate_picker_is_wired_to_multimodal_verifier():
    root = Path(__file__).resolve().parents[1]
    content = (root / "ios/FindTheRest/ContentView.swift").read_text()
    client = (root / "ios/FindTheRest/APIClient.swift").read_text()

    assert 'allowedContentTypes: [.movie]' in content
    assert 'Section("Verify a candidate clip")' in content
    assert 'verifyMediaPair(' in content
    assert 'verificationResult' in content
    assert 'v1/verify-media-pair' in client
