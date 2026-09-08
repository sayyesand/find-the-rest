from pathlib import Path

def test_ios_settings_exposes_backend_capabilities():
    root = Path(__file__).resolve().parents[1]
    content = (root / "ios/FindTheRest/ContentView.swift").read_text()
    client = (root / "ios/FindTheRest/APIClient.swift").read_text()
    models = (root / "ios/FindTheRest/APIModels.swift").read_text()

    assert 'Section("Backend capabilities")' in content
    assert 'capabilityRow("YouTube search"' in content
    assert 'capabilityRow("Push notifications"' in content
    assert 'Refresh Capabilities' in content
    assert 'v1/capabilities' in client
    assert 'struct CapabilitiesResponse' in models
