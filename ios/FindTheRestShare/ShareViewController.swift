import UIKit
import Social
import UniformTypeIdentifiers

private struct SharedVideoPayload: Codable {
    let url: String?
    let mediaFilename: String?
    let mediaKind: String?
    let createdAt: Date
}

final class ShareViewController: SLComposeServiceViewController {
    private let appGroup = "group.app.findtherest.shared"
    private let payloadKey = "pendingSharedVideo"
    private var sharedURL: URL?
    private var sharedMediaURL: URL?
    private var sharedMediaKind: String?
    private var pendingLoads = 0

    override func isContentValid() -> Bool { sharedURL != nil || sharedMediaURL != nil }

    override func viewDidLoad() {
        super.viewDidLoad()
        title = "Find the Rest"
        extractSharedContent()
    }

    private func extractSharedContent() {
        guard let items = extensionContext?.inputItems as? [NSExtensionItem] else { return }
        let providers = items.flatMap { $0.attachments ?? [] }
        for provider in providers {
            if sharedURL == nil && provider.hasItemConformingToTypeIdentifier(UTType.url.identifier) {
                pendingLoads += 1
                provider.loadItem(forTypeIdentifier: UTType.url.identifier, options: nil) { [weak self] value, _ in
                    DispatchQueue.main.async {
                        self?.sharedURL = value as? URL
                        self?.finishLoad()
                    }
                }
            }
            if sharedMediaURL == nil && provider.hasItemConformingToTypeIdentifier(UTType.movie.identifier) {
                pendingLoads += 1
                provider.loadFileRepresentation(forTypeIdentifier: UTType.movie.identifier) { [weak self] tempURL, _ in
                    guard let self, let tempURL,
                          let container = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: self.appGroup) else {
                        DispatchQueue.main.async { self?.finishLoad() }
                        return
                    }
                    let dest = container.appendingPathComponent("shared-\(UUID().uuidString).\(tempURL.pathExtension.isEmpty ? "mp4" : tempURL.pathExtension)")
                    try? FileManager.default.copyItem(at: tempURL, to: dest)
                    DispatchQueue.main.async {
                        self.sharedMediaURL = dest
                        self.sharedMediaKind = "video"
                        self.finishLoad()
                    }
                }
            }
            if sharedMediaURL == nil && provider.hasItemConformingToTypeIdentifier(UTType.image.identifier) {
                pendingLoads += 1
                provider.loadFileRepresentation(forTypeIdentifier: UTType.image.identifier) { [weak self] tempURL, _ in
                    guard let self, let tempURL,
                          let container = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: self.appGroup) else {
                        DispatchQueue.main.async { self?.finishLoad() }
                        return
                    }
                    let ext = tempURL.pathExtension.isEmpty ? "jpg" : tempURL.pathExtension
                    let dest = container.appendingPathComponent("shared-\(UUID().uuidString).\(ext)")
                    try? FileManager.default.copyItem(at: tempURL, to: dest)
                    DispatchQueue.main.async {
                        self.sharedMediaURL = dest
                        self.sharedMediaKind = "image"
                        self.finishLoad()
                    }
                }
            }
        }
        validateContent()
    }

    private func finishLoad() {
        pendingLoads = max(0, pendingLoads - 1)
        validateContent()
    }

    override func didSelectPost() {
        guard let defaults = UserDefaults(suiteName: appGroup) else {
            extensionContext?.cancelRequest(withError: NSError(domain: "FindTheRest", code: 2))
            return
        }
        let payload = SharedVideoPayload(url: sharedURL?.absoluteString, mediaFilename: sharedMediaURL?.lastPathComponent, mediaKind: sharedMediaKind, createdAt: Date())
        if let data = try? JSONEncoder().encode(payload) { defaults.set(data, forKey: payloadKey) }
        let deepLink = URL(string: "findtherest://shared")!
        extensionContext?.open(deepLink) { [weak self] _ in
            self?.extensionContext?.completeRequest(returningItems: nil)
        }
    }

    override func configurationItems() -> [Any]! { [] }
}
