import Foundation

struct SharedVideoPayload: Codable {
    let url: String?
    let mediaFilename: String?
    let mediaKind: String?
    let createdAt: Date
}

enum ShareHandoff {
    static let appGroup = "group.app.findtherest.shared"
    static let payloadKey = "pendingSharedVideo"

    static func consume() -> (payload: SharedVideoPayload, mediaURL: URL?)? {
        guard let defaults = UserDefaults(suiteName: appGroup),
              let data = defaults.data(forKey: payloadKey),
              let payload = try? JSONDecoder().decode(SharedVideoPayload.self, from: data) else { return nil }
        defaults.removeObject(forKey: payloadKey)
        let mediaURL: URL?
        if let name = payload.mediaFilename,
           let container = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroup) {
            mediaURL = container.appendingPathComponent(name)
        } else { mediaURL = nil }
        return (payload, mediaURL)
    }
}
