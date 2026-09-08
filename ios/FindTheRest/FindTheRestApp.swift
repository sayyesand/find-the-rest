import SwiftUI
import UIKit
import UserNotifications

enum PushRegistration {
    private static let installationKey = "findTheRestInstallationId"
    private static let tokenKey = "findTheRestPendingPushToken"

    static var installationId: String {
        if let existing = UserDefaults.standard.string(forKey: installationKey), !existing.isEmpty {
            return existing
        }
        let created = UUID().uuidString.lowercased()
        UserDefaults.standard.set(created, forKey: installationKey)
        return created
    }

    static func saveToken(_ token: String) {
        UserDefaults.standard.set(token, forKey: tokenKey)
    }

    static var savedToken: String? {
        UserDefaults.standard.string(forKey: tokenKey)
    }

    @MainActor
    static func requestAndRegister() async {
        do {
            let granted = try await UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .badge, .sound])
            if granted {
                UIApplication.shared.registerForRemoteNotifications()
                if let token = savedToken {
                    _ = try? await APIClient.shared.registerPushDevice(token: token)
                }
            }
        } catch {
            // Notification permission is optional; Find the Rest remains fully usable without it.
        }
    }
}

final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        PushRegistration.saveToken(token)
        Task {
            _ = try? await APIClient.shared.registerPushDevice(token: token)
        }
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        // Push is optional. Watch checks continue to work manually and through the scheduler.
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .sound]
    }
}

@main
struct FindTheRestApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            ContentView()
                .task {
                    await PushRegistration.requestAndRegister()
                }
        }
    }
}
