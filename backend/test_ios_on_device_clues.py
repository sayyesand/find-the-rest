from pathlib import Path

def test_ios_on_device_clue_extractor_and_private_search_path_are_wired():
    root = Path(__file__).resolve().parents[1]
    local = (root / "ios/FindTheRest/LocalMediaClues.swift").read_text()
    content = (root / "ios/FindTheRest/ContentView.swift").read_text()
    client = (root / "ios/FindTheRest/APIClient.swift").read_text()
    plist = (root / "ios/FindTheRest/Info.plist").read_text()
    pbx = (root / "ios/FindTheRest.xcodeproj/project.pbxproj").read_text()
    main = (root / "backend/app/main.py").read_text()

    assert "VNRecognizeTextRequest" in local
    assert "SFSpeechURLRecognitionRequest" in local
    assert "AVAssetImageGenerator" in local
    assert "LocalMediaClueExtractor.extract" in content
    assert "source media was not uploaded" in content
    assert "v1/analyze-clues" in client
    assert "NSSpeechRecognitionUsageDescription" in plist
    assert "LocalMediaClues.swift in Sources" in pbx
    assert '@app.post("/v1/analyze-clues"' in main


def test_on_device_clue_endpoint_does_not_cache_raw_clues():
    root = Path(__file__).resolve().parents[1]
    main = (root / "backend/app/main.py").read_text()
    start = main.index('@app.post("/v1/analyze-clues"')
    end = main.index('@app.post("/v1/share-analyze"', start)
    block = main[start:end]
    assert "cache_put" not in block
    assert "record_event" in block
    assert "source media itself did not need to be uploaded" in block
