from pathlib import Path


def test_ios_displays_calibrated_confidence_and_evidence_families():
    root = Path(__file__).resolve().parents[1]
    content = (root / "ios/FindTheRest/ContentView.swift").read_text()
    models = (root / "ios/FindTheRest/APIModels.swift").read_text()

    assert "Match confidence:" in content
    assert "independent evidence families" in content
    assert "confidenceGrade" in models
    assert "evidenceFamilyCount" in models
    assert "strongEvidenceFamilyCount" in models
