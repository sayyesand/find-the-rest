from pathlib import Path

from app.multimodal_verify import VerificationSignals, fuse_verification


def test_appearance_is_bounded_independent_verification_signal():
    base = fuse_verification(VerificationSignals(
        robust_visual=.70,
        boundary_visual=.60,
        scene_semantic=.60,
    ))
    with_appearance = fuse_verification(VerificationSignals(
        robust_visual=.70,
        boundary_visual=.60,
        scene_semantic=.60,
        appearance_similarity=.82,
        has_appearance=True,
    ))
    assert with_appearance.confidence > base.confidence
    assert with_appearance.confidence - base.confidence < .15


def test_api_notes_explicitly_disallow_identity_database():
    root = Path(__file__).resolve().parents[1]
    main = (root / "backend/app/main.py").read_text()
    appearance = (root / "backend/app/appearance.py").read_text()
    assert '@app.post("/v1/compare-appearance"' in main
    assert "No reusable biometric profile or face database is created or retained." in main
    assert "does not identify a person" in appearance


def test_ios_displays_appearance_without_identity_claim():
    root = Path(__file__).resolve().parents[1]
    models = (root / "ios/FindTheRest/APIModels.swift").read_text()
    content = (root / "ios/FindTheRest/ContentView.swift").read_text()
    assert "appearanceSimilarity" in models
    assert "faceRegionSimilarity" in models
    assert "clothingRegionSimilarity" in models
    assert "Appearance matching does not identify or name a person." in content
