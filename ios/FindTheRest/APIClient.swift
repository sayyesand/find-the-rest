import Foundation
import Security

final class APIClient {
    static let shared = APIClient()
    private let backendKey = "findTheRestBackendURL"
    private let apiKeyKey = "findTheRestAPIKey"
    private let defaultBackendURL = "https://find-the-rest-api.onrender.com"

    var baseURL: URL {
        if let raw = UserDefaults.standard.string(forKey: backendKey),
           let url = URL(string: raw), url.scheme == "https" {
            return url
        }
        return URL(string: defaultBackendURL)!
    }

    func setBaseURL(_ raw: String) throws {
        guard let url = URL(string: raw.trimmingCharacters(in: .whitespacesAndNewlines)),
              url.scheme == "https", url.host != nil else {
            throw URLError(.badURL)
        }
        UserDefaults.standard.set(url.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")), forKey: backendKey)
    }

    var configuredBaseURLString: String {
        UserDefaults.standard.string(forKey: backendKey) ?? defaultBackendURL
    }

    var configuredAPIKey: String {
        if let data = keychainRead(apiKeyKey),
           let value = String(data: data, encoding: .utf8) {
            return value
        }
        // One-time migration from older beta builds.
        if let legacy = UserDefaults.standard.string(forKey: apiKeyKey), !legacy.isEmpty {
            setAPIKey(legacy)
            UserDefaults.standard.removeObject(forKey: apiKeyKey)
            return legacy
        }
        return ""
    }

    func setAPIKey(_ raw: String) {
        let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if value.isEmpty {
            keychainDelete(apiKeyKey)
        } else {
            keychainWrite(apiKeyKey, Data(value.utf8))
        }
        UserDefaults.standard.removeObject(forKey: apiKeyKey)
    }

    private func keychainRead(_ account: String) -> Data? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "FindTheRest",
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: CFTypeRef?
        return SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess ? result as? Data : nil
    }

    private func keychainWrite(_ account: String, _ data: Data) {
        keychainDelete(account)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "FindTheRest",
            kSecAttrAccount as String: account,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        ]
        SecItemAdd(query as CFDictionary, nil)
    }

    private func keychainDelete(_ account: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "FindTheRest",
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
    }

    private func authorize(_ request: inout URLRequest) {
        let key = configuredAPIKey
        if !key.isEmpty { request.setValue(key, forHTTPHeaderField: "X-FindTheRest-Key") }
    }

    func health() async throws -> Bool {
        try ensureConfigured()
        var request = URLRequest(url: baseURL.appendingPathComponent("health"))
        request.timeoutInterval = 12
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response, data: data)
        let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return object?["ok"] as? Bool == true
    }



    func betaReadiness() async throws -> BetaReadinessResponse {
        try ensureConfigured()
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/beta-readiness"))
        request.timeoutInterval = 20
        authorize(&request)
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response, data: data)
        return try JSONDecoder().decode(BetaReadinessResponse.self, from: data)
    }


    func capabilities() async throws -> CapabilitiesResponse {
        try ensureConfigured()
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/capabilities"))
        request.timeoutInterval = 15
        authorize(&request)
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response, data: data)
        return try JSONDecoder().decode(CapabilitiesResponse.self, from: data)
    }


    func analyzeWithLocalClues(
        url: URL,
        scope: String = "web",
        intent: String = "continue_story",
        transcript: String?,
        visibleText: String?
    ) async throws -> AnalyzeResponse {
        try ensureConfigured()
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/analyze-clues"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        authorize(&request)
        request.httpBody = try JSONEncoder().encode(LocalClueAnalyzeRequest(
            url: url.absoluteString,
            scope: scope,
            intent: intent,
            transcript: transcript,
            visibleText: visibleText
        ))
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(AnalyzeResponse.self, from: data)
    }

    func analyze(url: URL, scope: String = "web", intent: String = "continue_story") async throws -> AnalyzeResponse {
        try ensureConfigured()
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/analyze"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        authorize(&request)
        request.httpBody = try JSONEncoder().encode(AnalyzeRequest(url: url.absoluteString, scope: scope, intent: intent))
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(AnalyzeResponse.self, from: data)
    }

    func analyzeShared(url: URL?, mediaURL: URL?, scope: String = "web", intent: String = "continue_story") async throws -> AnalyzeResponse {
        try ensureConfigured()
        guard url != nil || mediaURL != nil else { throw URLError(.badURL) }
        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/share-analyze"))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        authorize(&request)
        var body = Data()
        func field(_ name: String, _ value: String) {
            body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".data(using: .utf8)!)
        }
        if let url { field("url", url.absoluteString) }
        field("scope", scope)
        field("intent", intent)
        if let mediaURL {
            let access = mediaURL.startAccessingSecurityScopedResource()
            defer { if access { mediaURL.stopAccessingSecurityScopedResource() } }
            let data = try Data(contentsOf: mediaURL)
            let ext = mediaURL.pathExtension.lowercased()
            let mime: String
            switch ext {
            case "jpg", "jpeg": mime = "image/jpeg"
            case "png": mime = "image/png"
            case "webp": mime = "image/webp"
            case "heic", "heif": mime = "image/heic"
            default: mime = "video/mp4"
            }
            body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"source\"; filename=\"\(mediaURL.lastPathComponent)\"\r\nContent-Type: \(mime)\r\n\r\n".data(using: .utf8)!)
            body.append(data)
            body.append("\r\n".data(using: .utf8)!)
        }
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(AnalyzeResponse.self, from: data)
    }


    func visualFingerprint(mediaURL: URL) async throws -> VisualFingerprintResponse {
        try ensureConfigured()
        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/visual-fingerprint"))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        authorize(&request)

        let access = mediaURL.startAccessingSecurityScopedResource()
        defer { if access { mediaURL.stopAccessingSecurityScopedResource() } }
        let data = try Data(contentsOf: mediaURL)
        let ext = mediaURL.pathExtension.lowercased()
        let mime: String
        switch ext {
        case "jpg", "jpeg": mime = "image/jpeg"
        case "png": mime = "image/png"
        case "webp": mime = "image/webp"
        case "heic", "heif": mime = "image/heic"
        default: mime = "video/mp4"
        }

        var body = Data()
        body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"media\"; filename=\"\(mediaURL.lastPathComponent)\"\r\nContent-Type: \(mime)\r\n\r\n".data(using: .utf8)!)
        body.append(data)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (responseData, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(VisualFingerprintResponse.self, from: responseData)
    }


    func extractVisibleText(mediaURL: URL) async throws -> VisibleTextResponse {
        try ensureConfigured()
        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/extract-visible-text"))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        authorize(&request)

        let access = mediaURL.startAccessingSecurityScopedResource()
        defer { if access { mediaURL.stopAccessingSecurityScopedResource() } }
        let data = try Data(contentsOf: mediaURL)
        let ext = mediaURL.pathExtension.lowercased()
        let mime: String
        switch ext {
        case "jpg", "jpeg": mime = "image/jpeg"
        case "png": mime = "image/png"
        case "webp": mime = "image/webp"
        case "heic", "heif": mime = "image/heic"
        default: mime = "video/mp4"
        }

        var body = Data()
        body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"media\"; filename=\"\(mediaURL.lastPathComponent)\"\r\nContent-Type: \(mime)\r\n\r\n".data(using: .utf8)!)
        body.append(data)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (responseData, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(VisibleTextResponse.self, from: responseData)
    }


    func discoverMedia(mediaURL: URL) async throws -> MediaDiscoveryResponse {
        try ensureConfigured()
        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/discover-media"))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        authorize(&request)

        let access = mediaURL.startAccessingSecurityScopedResource()
        defer { if access { mediaURL.stopAccessingSecurityScopedResource() } }
        let data = try Data(contentsOf: mediaURL)
        let ext = mediaURL.pathExtension.lowercased()
        let mime: String
        switch ext {
        case "jpg", "jpeg": mime = "image/jpeg"
        case "png": mime = "image/png"
        case "webp": mime = "image/webp"
        case "heic", "heif": mime = "image/heic"
        default: mime = "video/mp4"
        }

        var body = Data()
        body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"media\"; filename=\"\(mediaURL.lastPathComponent)\"\r\nContent-Type: \(mime)\r\n\r\n".data(using: .utf8)!)
        body.append(data)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (responseData, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(MediaDiscoveryResponse.self, from: responseData)
    }


    func submitFeedback(_ feedback: FeedbackRequest) async throws -> FeedbackResponse {
        try ensureConfigured()
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/feedback"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        authorize(&request)
        request.httpBody = try JSONEncoder().encode(feedback)
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(FeedbackResponse.self, from: data)
    }



    func registerPushDevice(token: String) async throws -> PushRegisterResponse {
        try ensureConfigured()
        #if DEBUG
        let environment = "sandbox"
        #else
        let environment = "production"
        #endif
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/push/register"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        authorize(&request)
        request.httpBody = try JSONEncoder().encode(PushRegisterRequest(
            installationId: PushRegistration.installationId,
            deviceToken: token,
            environment: environment
        ))
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(PushRegisterResponse.self, from: data)
    }

    func createWatch(sourceURL: String, scope: String = "web", intent: String = "continue_story") async throws -> WatchStatusResponse {
        try ensureConfigured()
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/watch"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        authorize(&request)
        request.httpBody = try JSONEncoder().encode(WatchCreateRequest(sourceUrl: sourceURL, scope: scope, intent: intent, installationId: PushRegistration.installationId))
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(WatchStatusResponse.self, from: data)
    }

    func checkWatch(watchId: String) async throws -> WatchCheckResponse {
        try ensureConfigured()
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/watch/\(watchId)/check"))
        request.httpMethod = "POST"
        authorize(&request)
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(WatchCheckResponse.self, from: data)
    }


    func listWatches() async throws -> WatchListResponse {
        try ensureConfigured()
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/watches"))
        authorize(&request)
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(WatchListResponse.self, from: data)
    }

    func removeWatch(watchId: String) async throws -> WatchDeleteResponse {
        try ensureConfigured()
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/watch/\(watchId)"))
        request.httpMethod = "DELETE"
        authorize(&request)
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(WatchDeleteResponse.self, from: data)
    }




    func verifyRankedCandidates(
        sourceURL: URL,
        candidates: [Candidate],
        sourceTranscript: String? = nil
    ) async throws -> VerificationRerankResponse {
        try ensureConfigured()
        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/verify-ranked-candidates"))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        authorize(&request)

        let encoded = try JSONEncoder().encode(Array(candidates.prefix(3)))
        guard let candidatesJSON = String(data: encoded, encoding: .utf8) else {
            throw URLError(.cannotEncodeContentData)
        }

        let access = sourceURL.startAccessingSecurityScopedResource()
        defer { if access { sourceURL.stopAccessingSecurityScopedResource() } }
        let data = try Data(contentsOf: sourceURL)
        let ext = sourceURL.pathExtension.lowercased()
        let mime: String
        switch ext {
        case "mov": mime = "video/quicktime"
        case "m4v": mime = "video/x-m4v"
        default: mime = "video/mp4"
        }

        var body = Data()
        func field(_ name: String, _ value: String) {
            body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".data(using: .utf8)!)
        }
        field("candidates_json", candidatesJSON)
        if let sourceTranscript, !sourceTranscript.isEmpty {
            field("source_transcript", sourceTranscript)
        }
        body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"source\"; filename=\"\(sourceURL.lastPathComponent)\"\r\nContent-Type: \(mime)\r\n\r\n".data(using: .utf8)!)
        body.append(data)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (responseData, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(VerificationRerankResponse.self, from: responseData)
    }


    func verifyCandidateURL(
        sourceURL: URL,
        candidateURL: String,
        sourceTranscript: String? = nil
    ) async throws -> CandidateURLVerifyResponse {
        try ensureConfigured()
        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/verify-candidate-url"))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        authorize(&request)

        let access = sourceURL.startAccessingSecurityScopedResource()
        defer { if access { sourceURL.stopAccessingSecurityScopedResource() } }
        let data = try Data(contentsOf: sourceURL)
        let ext = sourceURL.pathExtension.lowercased()
        let mime: String
        switch ext {
        case "mov": mime = "video/quicktime"
        case "m4v": mime = "video/x-m4v"
        default: mime = "video/mp4"
        }

        var body = Data()
        func field(_ name: String, _ value: String) {
            body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".data(using: .utf8)!)
        }
        field("candidate_url", candidateURL)
        if let sourceTranscript, !sourceTranscript.isEmpty {
            field("source_transcript", sourceTranscript)
        }
        body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"source\"; filename=\"\(sourceURL.lastPathComponent)\"\r\nContent-Type: \(mime)\r\n\r\n".data(using: .utf8)!)
        body.append(data)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (responseData, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(CandidateURLVerifyResponse.self, from: responseData)
    }

    func verifyMediaPair(sourceURL: URL, candidateURL: URL) async throws -> MultimodalVerifyResponse {
        try ensureConfigured()
        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/verify-media-pair"))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        authorize(&request)

        func mimeType(for url: URL) -> String {
            switch url.pathExtension.lowercased() {
            case "mov": return "video/quicktime"
            case "m4v": return "video/x-m4v"
            default: return "video/mp4"
            }
        }

        func appendFile(_ name: String, _ url: URL, to body: inout Data) throws {
            let access = url.startAccessingSecurityScopedResource()
            defer { if access { url.stopAccessingSecurityScopedResource() } }
            let data = try Data(contentsOf: url)
            body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"; filename=\"\(url.lastPathComponent)\"\r\nContent-Type: \(mimeType(for: url))\r\n\r\n".data(using: .utf8)!)
            body.append(data)
            body.append("\r\n".data(using: .utf8)!)
        }

        var body = Data()
        try appendFile("source", sourceURL, to: &body)
        try appendFile("candidate", candidateURL, to: &body)
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(MultimodalVerifyResponse.self, from: data)
    }

    private func ensureConfigured() throws {
        if baseURL.host == "example.invalid" { throw BackendConfigurationError.missingURL }
    }

    private func validate(_ response: URLResponse, data: Data? = nil) throws {
        guard let http = response as? HTTPURLResponse else {
            throw BackendServiceError.invalidResponse
        }
        guard 200..<300 ~= http.statusCode else {
            let detail: String?
            if let data,
               let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                detail = object["detail"] as? String
            } else {
                detail = nil
            }
            switch http.statusCode {
            case 401, 403: throw BackendServiceError.authentication
            case 413: throw BackendServiceError.mediaTooLarge
            case 415: throw BackendServiceError.unsupportedMedia
            case 429: throw BackendServiceError.rateLimited
            case 500...599: throw BackendServiceError.serverUnavailable
            default: throw BackendServiceError.http(http.statusCode, detail)
            }
        }
    }
}

enum BackendServiceError: LocalizedError {
    case invalidResponse
    case authentication
    case mediaTooLarge
    case unsupportedMedia
    case rateLimited
    case serverUnavailable
    case http(Int, String?)

    var errorDescription: String? {
        switch self {
        case .invalidResponse: return "The backend returned an invalid response."
        case .authentication: return "The backend rejected the API key. Check Settings."
        case .mediaTooLarge: return "This media file is too large for the beta backend."
        case .unsupportedMedia: return "This media format is not supported by the beta backend."
        case .rateLimited: return "The search service is busy. Try again shortly."
        case .serverUnavailable: return "The Find the Rest backend is temporarily unavailable."
        case let .http(code, detail):
            return detail?.isEmpty == false ? detail : "Backend request failed (HTTP \(code))."
        }
    }
}

enum BackendConfigurationError: LocalizedError {
    case missingURL
    var errorDescription: String? { "Set your deployed HTTPS backend URL in Settings first." }
}
