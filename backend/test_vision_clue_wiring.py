from pathlib import Path


def test_backend_has_visual_clue_endpoint_and_discovery_fusion():
    root=Path(__file__).resolve().parents[1]
    main=(root/"backend/app/main.py").read_text()
    discovery=(root/"backend/app/media_discovery.py").read_text()
    assert '@app.post("/v1/extract-visual-clues"' in main
    assert "visual_objects=list(semantic_visual.objects)" in main
    assert '"visual_clue_match"' in discovery
    assert '"multimodal_agreement"' in discovery


def test_ios_displays_visual_clues():
    root=Path(__file__).resolve().parents[1]
    models=(root/"ios/FindTheRest/APIModels.swift").read_text()
    content=(root/"ios/FindTheRest/ContentView.swift").read_text()
    for value in ("visualObjects","visualLogos","visualScenes","visualClothing"):
        assert value in models
    assert 'Section("Visual clues")' in content
    assert 'detailRow("Objects", discovery.visualObjects)' in content
    assert 'detailRow("Logos", discovery.visualLogos)' in content
