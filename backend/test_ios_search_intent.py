from pathlib import Path


def test_ios_search_goal_picker_and_api_intent_are_wired():
    root = Path(__file__).resolve().parents[1]
    content = (root / "ios/FindTheRest/ContentView.swift").read_text()
    client = (root / "ios/FindTheRest/APIClient.swift").read_text()
    models = (root / "ios/FindTheRest/APIModels.swift").read_text()

    assert 'Picker("I want to", selection: $searchIntent)' in content
    assert 'Text("Continue the story").tag("continue_story")' in content
    assert 'Text("Watch the full original").tag("full_original")' in content
    assert 'Text("Find the original source").tag("original_source")' in content
    assert 'Text("Find other copies").tag("other_copies")' in content
    assert 'Text("Identify what’s shown").tag("identify_shown")' in content
    assert "intent: searchIntent" in content
    assert "let intent: String" in models
    assert 'field("intent", intent)' in client


def test_watch_creation_preserves_result_intent():
    root = Path(__file__).resolve().parents[1]
    content = (root / "ios/FindTheRest/ContentView.swift").read_text()
    assert "createWatch(sourceURL: result.sourceUrl, intent: result.searchIntent)" in content
