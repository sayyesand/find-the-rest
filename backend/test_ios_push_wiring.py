from pathlib import Path

def test_ios_push_registration_and_entitlement_are_wired():
    root = Path(__file__).resolve().parents[1]
    app = (root / "ios/FindTheRest/FindTheRestApp.swift").read_text()
    client = (root / "ios/FindTheRest/APIClient.swift").read_text()
    ent = (root / "ios/FindTheRest/FindTheRest.entitlements").read_text()
    pbx = (root / "ios/FindTheRest.xcodeproj/project.pbxproj").read_text()

    assert "registerForRemoteNotifications" in app
    assert "didRegisterForRemoteNotificationsWithDeviceToken" in app
    assert "v1/push/register" in client
    assert "installationId: PushRegistration.installationId" in client
    assert "aps-environment" in ent
    assert "APS_ENVIRONMENT = development;" in pbx
    assert "APS_ENVIRONMENT = production;" in pbx
