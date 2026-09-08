from pathlib import Path


def test_ios_has_goal_specific_result_language_and_actions():
    root = Path(__file__).resolve().parents[1]
    content = (root / "ios/FindTheRest/ContentView.swift").read_text()
    for state in (
        "original_source_found",
        "copies_found",
        "identification_found",
        "no_verified_full_original",
        "no_verified_source",
        "no_verified_copy",
        "no_verified_identification",
    ):
        assert state in content
    assert 'case "find_original_source": return "Find original source"' in content
    assert 'case "open_original_source": return "Open original source"' in content


def test_watch_button_is_continuation_goal_only():
    root = Path(__file__).resolve().parents[1]
    content = (root / "ios/FindTheRest/ContentView.swift").read_text()
    assert 'result.searchIntent == "continue_story"' in content
