import Foundation

struct AnalyzeRequest: Codable {
    let url: String
    let scope: String
    let intent: String
}

struct LocalClueAnalyzeRequest: Codable {
    let url: String
    let scope: String
    let intent: String
    let transcript: String?
    let visibleText: String?

    enum CodingKeys: String, CodingKey {
        case url, scope, intent, transcript
        case visibleText = "visible_text"
    }
}

struct Candidate: Codable, Identifiable {
    var id: String { url }
    let title: String
    let url: String
    let platform: String
    let creator: String?
    let publishedAt: String?
    let thumbnailUrl: String?
    let reason: String
    let snippet: String?
    let score: Double
    let evidence: [String: Double]?
    let matchedDetails: [String: [String]]?
    let durationSeconds: Double?
    let traceRole: String?
    let traceScore: Double?

    enum CodingKeys: String, CodingKey {
        case title, url, platform, creator, reason, snippet, score, evidence
        case matchedDetails = "matched_details"
        case publishedAt = "published_at"
        case thumbnailUrl = "thumbnail_url"
        case durationSeconds = "duration_seconds"
        case traceRole = "trace_role"
        case traceScore = "trace_score"
    }
}



struct ChainNode: Codable, Identifiable {
    var id: String { candidate.url + "-" + String(inferredPart ?? 0) }
    let candidate: Candidate
    let inferredPart: Int?
    let episodeNumber: Int?
    let relationship: String
    let chainScore: Double
    let orderReason: String

    enum CodingKeys: String, CodingKey {
        case candidate, relationship
        case inferredPart = "inferred_part"
        case episodeNumber = "episode_number"
        case chainScore = "chain_score"
        case orderReason = "order_reason"
    }
}

struct ProvenanceNode: Codable, Identifiable {
    var id: String { nodeId }
    let nodeId: String
    let label: String
    let url: String
    let role: String
    let score: Double
    let creator: String?
    let publishedAt: String?

    enum CodingKeys: String, CodingKey {
        case label, url, role, score, creator
        case nodeId = "node_id"
        case publishedAt = "published_at"
    }
}

struct ProvenanceEdge: Codable, Identifiable {
    var id: String { fromId + ">" + toId + ":" + relationship }
    let fromId: String
    let toId: String
    let relationship: String
    let confidence: Double
    let reasons: [String]

    enum CodingKeys: String, CodingKey {
        case relationship, confidence, reasons
        case fromId = "from_id"
        case toId = "to_id"
    }
}

struct ProvenanceGraph: Codable {
    let nodes: [ProvenanceNode]
    let edges: [ProvenanceEdge]
    let likelyOriginNodeId: String?
    let confidence: Double

    enum CodingKeys: String, CodingKey {
        case nodes, edges, confidence
        case likelyOriginNodeId = "likely_origin_node_id"
    }
}

struct SearchCoverage: Codable {
    let providerConfigured: Bool
    let attempted: Int
    let completed: Int
    let failed: Int
    let coverageRatio: Double
    let broadEnoughForNonpublicationHint: Bool

    enum CodingKeys: String, CodingKey {
        case attempted, completed, failed
        case providerConfigured = "provider_configured"
        case coverageRatio = "coverage_ratio"
        case broadEnoughForNonpublicationHint = "broad_enough_for_nonpublication_hint"
    }
}

struct AnalyzeResponse: Codable {
    let searchId: String?
    let searchIntent: String
    let sourcePlatform: String
    let sourceUrl: String
    let matchType: String
    let confidence: Double
    let confidenceGrade: String
    let evidenceFamilyCount: Int
    let strongEvidenceFamilyCount: Int
    let bestMatch: Candidate?
    let candidates: [Candidate]
    let continuationChain: [ChainNode]
    let chainConfidence: Double
    let missingParts: [Int]
    let recoveredParts: [Int]
    let resultState: String
    let resultMessage: String
    let resultStateConfidence: Double
    let availableActions: [String]
    let provenanceGraph: ProvenanceGraph?
    let searchCoverage: SearchCoverage
    let notes: [String]

    enum CodingKeys: String, CodingKey {
        case confidence, candidates, notes
        case confidenceGrade = "confidence_grade"
        case evidenceFamilyCount = "evidence_family_count"
        case strongEvidenceFamilyCount = "strong_evidence_family_count"
        case searchId = "search_id"
        case searchIntent = "search_intent"
        case sourcePlatform = "source_platform"
        case sourceUrl = "source_url"
        case matchType = "match_type"
        case bestMatch = "best_match"
        case continuationChain = "continuation_chain"
        case chainConfidence = "chain_confidence"
        case missingParts = "missing_parts"
        case recoveredParts = "recovered_parts"
        case resultState = "result_state"
        case resultMessage = "result_message"
        case resultStateConfidence = "result_state_confidence"
        case availableActions = "available_actions"
        case provenanceGraph = "provenance_graph"
        case searchCoverage = "search_coverage"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        searchId = try c.decodeIfPresent(String.self, forKey: .searchId)
        searchIntent = try c.decodeIfPresent(String.self, forKey: .searchIntent) ?? "continue_story"
        sourcePlatform = try c.decode(String.self, forKey: .sourcePlatform)
        sourceUrl = try c.decode(String.self, forKey: .sourceUrl)
        matchType = try c.decode(String.self, forKey: .matchType)
        confidence = try c.decodeIfPresent(Double.self, forKey: .confidence) ?? 0
        confidenceGrade = try c.decodeIfPresent(String.self, forKey: .confidenceGrade) ?? "low"
        evidenceFamilyCount = try c.decodeIfPresent(Int.self, forKey: .evidenceFamilyCount) ?? 0
        strongEvidenceFamilyCount = try c.decodeIfPresent(Int.self, forKey: .strongEvidenceFamilyCount) ?? 0
        bestMatch = try c.decodeIfPresent(Candidate.self, forKey: .bestMatch)
        candidates = try c.decodeIfPresent([Candidate].self, forKey: .candidates) ?? []
        continuationChain = try c.decodeIfPresent([ChainNode].self, forKey: .continuationChain) ?? []
        chainConfidence = try c.decodeIfPresent(Double.self, forKey: .chainConfidence) ?? 0
        missingParts = try c.decodeIfPresent([Int].self, forKey: .missingParts) ?? []
        recoveredParts = try c.decodeIfPresent([Int].self, forKey: .recoveredParts) ?? []
        resultState = try c.decodeIfPresent(String.self, forKey: .resultState) ?? "no_verified_match"
        resultMessage = try c.decodeIfPresent(String.self, forKey: .resultMessage) ?? ""
        resultStateConfidence = try c.decodeIfPresent(Double.self, forKey: .resultStateConfidence) ?? 0
        availableActions = try c.decodeIfPresent([String].self, forKey: .availableActions) ?? []
        provenanceGraph = try c.decodeIfPresent(ProvenanceGraph.self, forKey: .provenanceGraph)
        searchCoverage = try c.decodeIfPresent(SearchCoverage.self, forKey: .searchCoverage) ?? SearchCoverage(
            providerConfigured: false,
            attempted: 0,
            completed: 0,
            failed: 0,
            coverageRatio: 0,
            broadEnoughForNonpublicationHint: false
        )
        notes = try c.decodeIfPresent([String].self, forKey: .notes) ?? []
    }
}


struct VisualFingerprintResponse: Codable {
    let mediaKind: String
    let representativeFrames: Int
    let ahashes: [String]
    let dhashes: [String]
    let notes: [String]

    enum CodingKeys: String, CodingKey {
        case ahashes, dhashes, notes
        case mediaKind = "media_kind"
        case representativeFrames = "representative_frames"
    }
}


struct VisibleTextResponse: Codable {
    let text: String
    let handles: [String]
    let hashtags: [String]
    let urls: [String]
    let keywords: [String]
    let suggestedQueries: [String]
    let framesExamined: Int
    let backend: String
    let notes: [String]

    enum CodingKeys: String, CodingKey {
        case text, handles, hashtags, urls, keywords, backend, notes
        case suggestedQueries = "suggested_queries"
        case framesExamined = "frames_examined"
    }
}


struct MediaDiscoveryResponse: Codable {
    let searchId: String?
    let mediaKind: String
    let confidence: Double
    let bestMatch: Candidate?
    let candidates: [Candidate]
    let visibleText: String
    let handles: [String]
    let keywords: [String]
    let visualObjects: [String]
    let visualLogos: [String]
    let visualScenes: [String]
    let visualClothing: [String]
    let representativeFrames: Int
    let notes: [String]

    enum CodingKeys: String, CodingKey {
        case confidence, candidates, handles, keywords, notes
        case searchId = "search_id"
        case mediaKind = "media_kind"
        case bestMatch = "best_match"
        case visibleText = "visible_text"
        case visualObjects = "visual_objects"
        case visualLogos = "visual_logos"
        case visualScenes = "visual_scenes"
        case visualClothing = "visual_clothing"
        case representativeFrames = "representative_frames"
    }
}


struct FeedbackRequest: Codable {
    let searchId: String
    let verdict: String
    let bestMatchUrl: String?
    let sourcePlatform: String?
    let confidence: Double?
    let searchIntent: String
    let resultState: String?
    let confidenceGrade: String
    let evidenceFamilyCount: Int
    let strongEvidenceFamilyCount: Int

    enum CodingKeys: String, CodingKey {
        case verdict, confidence
        case searchId = "search_id"
        case bestMatchUrl = "best_match_url"
        case sourcePlatform = "source_platform"
        case searchIntent = "search_intent"
        case resultState = "result_state"
        case confidenceGrade = "confidence_grade"
        case evidenceFamilyCount = "evidence_family_count"
        case strongEvidenceFamilyCount = "strong_evidence_family_count"
    }
}

struct FeedbackResponse: Codable {
    let accepted: Bool
    let notes: [String]
}


struct WatchCreateRequest: Codable {
    let sourceUrl: String
    let scope: String
    let intent: String
    let installationId: String?

    enum CodingKeys: String, CodingKey {
        case scope, intent
        case sourceUrl = "source_url"
        case installationId = "installation_id"
    }
}

struct WatchStatusResponse: Codable {
    let watchId: String
    let sourceUrl: String
    let scope: String
    let intent: String
    let createdAt: String
    let lastCheckedAt: String?
    let lastResultState: String?
    let lastBestMatchUrl: String?
    let active: Bool
    let found: Bool
    let message: String

    enum CodingKeys: String, CodingKey {
        case scope, intent, active, found, message
        case watchId = "watch_id"
        case sourceUrl = "source_url"
        case createdAt = "created_at"
        case lastCheckedAt = "last_checked_at"
        case lastResultState = "last_result_state"
        case lastBestMatchUrl = "last_best_match_url"
    }
}

struct WatchCheckResponse: Codable {
    let watch: WatchStatusResponse
    let result: AnalyzeResponse?
}


struct WatchListResponse: Codable {
    let watches: [WatchStatusResponse]
}

struct WatchDeleteResponse: Codable {
    let removed: Bool
    let watchId: String
    let message: String

    enum CodingKeys: String, CodingKey {
        case removed, message
        case watchId = "watch_id"
    }
}


struct MultimodalVerifyResponse: Codable {
    let verdict: String
    let confidence: Double
    let agreementCount: Int
    let contradictionPenalty: Double
    let robustVisualSimilarity: Double
    let audioFingerprintSimilarity: Double
    let boundaryVisualContinuity: Double
    let boundaryAudioContinuity: Double
    let transcriptSemantic: Double
    let sceneSemantic: Double
    let appearanceSimilarity: Double
    let faceRegionSimilarity: Double
    let clothingRegionSimilarity: Double
    let contributions: [String: Double]
    let transcriptBackend: String
    let notes: [String]

    enum CodingKeys: String, CodingKey {
        case verdict, confidence, contributions, notes
        case agreementCount = "agreement_count"
        case contradictionPenalty = "contradiction_penalty"
        case robustVisualSimilarity = "robust_visual_similarity"
        case audioFingerprintSimilarity = "audio_fingerprint_similarity"
        case boundaryVisualContinuity = "boundary_visual_continuity"
        case boundaryAudioContinuity = "boundary_audio_continuity"
        case transcriptSemantic = "transcript_semantic"
        case sceneSemantic = "scene_semantic"
        case appearanceSimilarity = "appearance_similarity"
        case faceRegionSimilarity = "face_region_similarity"
        case clothingRegionSimilarity = "clothing_region_similarity"
        case transcriptBackend = "transcript_backend"
    }
}


struct PushRegisterRequest: Codable {
    let installationId: String
    let deviceToken: String
    let environment: String

    enum CodingKeys: String, CodingKey {
        case environment
        case installationId = "installation_id"
        case deviceToken = "device_token"
    }
}

struct PushRegisterResponse: Codable {
    let registered: Bool
    let installationId: String
    let tokenFingerprint: String
    let pushConfigured: Bool
    let notes: [String]

    enum CodingKeys: String, CodingKey {
        case registered, notes
        case installationId = "installation_id"
        case tokenFingerprint = "token_fingerprint"
        case pushConfigured = "push_configured"
    }
}


struct CapabilitiesResponse: Codable {
    let youtubeSearch: Bool
    let openWebSearch: Bool
    let reverseImageSearch: Bool
    let localTranscription: Bool
    let watchStore: Bool
    let feedbackStore: Bool
    let pushNotifications: Bool
    let watchStorageBackend: String
    let candidateMediaVerification: Bool
    let notes: [String]

    enum CodingKeys: String, CodingKey {
        case notes
        case youtubeSearch = "youtube_search"
        case openWebSearch = "open_web_search"
        case reverseImageSearch = "reverse_image_search"
        case localTranscription = "local_transcription"
        case watchStore = "watch_store"
        case feedbackStore = "feedback_store"
        case pushNotifications = "push_notifications"
        case watchStorageBackend = "watch_storage_backend"
        case candidateMediaVerification = "candidate_media_verification"
    }
}



struct VerificationRankedCandidateResponse: Codable, Identifiable {
    var id: String { candidate.url }
    let candidate: Candidate
    let originalScore: Double
    let adjustedScore: Double
    let delta: Double
    let disposition: String
    let providerStatus: String
    let verification: MultimodalVerifyResponse?

    enum CodingKeys: String, CodingKey {
        case candidate, delta, disposition, verification
        case originalScore = "original_score"
        case adjustedScore = "adjusted_score"
        case providerStatus = "provider_status"
    }
}

struct VerificationRerankResponse: Codable {
    let ranked: [VerificationRankedCandidateResponse]
    let verifiedCount: Int
    let providerAttempts: Int
    let changedTopCandidate: Bool
    let topCandidateUrl: String?
    let notes: [String]

    enum CodingKeys: String, CodingKey {
        case ranked, notes
        case verifiedCount = "verified_count"
        case providerAttempts = "provider_attempts"
        case changedTopCandidate = "changed_top_candidate"
        case topCandidateUrl = "top_candidate_url"
    }
}

struct CandidateURLVerifyResponse: Codable {
    let candidateUrl: String
    let providerStatus: String
    let verified: Bool
    let verification: MultimodalVerifyResponse?
    let notes: [String]

    enum CodingKeys: String, CodingKey {
        case verified, verification, notes
        case candidateUrl = "candidate_url"
        case providerStatus = "provider_status"
    }
}


struct BetaReadinessGateResponse: Codable, Identifiable {
    var id: String { gateId }
    let gateId: String
    let label: String
    let passed: Bool
    let critical: Bool
    let detail: String

    enum CodingKeys: String, CodingKey {
        case label, passed, critical, detail
        case gateId = "gate_id"
    }
}

struct BetaReadinessResponse: Codable {
    let betaReady: Bool
    let criticalPassed: Int
    let criticalTotal: Int
    let passed: Int
    let total: Int
    let benchmarkPassRate: Double
    let gates: [BetaReadinessGateResponse]
    let notes: [String]

    enum CodingKeys: String, CodingKey {
        case passed, total, gates, notes
        case betaReady = "beta_ready"
        case criticalPassed = "critical_passed"
        case criticalTotal = "critical_total"
        case benchmarkPassRate = "benchmark_pass_rate"
    }
}
