import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @State private var urlText = ""
    @State private var result: AnalyzeResponse?
    @State private var loading = false
    @State private var error: String?
    @State private var sharedMediaURL: URL?
    @State private var sharedMediaKind: String?
    @State private var visualResult: VisualFingerprintResponse?
    @State private var visibleTextResult: VisibleTextResponse?
    @State private var mediaDiscovery: MediaDiscoveryResponse?
    @State private var shareStatus: String?
    @State private var showingSettings = false
    @State private var showingWatches = false
    @State private var feedbackStatus: String?
    @State private var watchStatus: WatchStatusResponse?
    @State private var watchMessage: String?
    @State private var showingCandidatePicker = false
    @State private var verificationResult: MultimodalVerifyResponse?
    @State private var verificationRerank: VerificationRerankResponse?
    @State private var verificationStatus: String?
    @State private var verifyingCandidate = false
    @State private var lastLocalTranscript: String?
    @State private var searchIntent = "continue_story"

    var body: some View {
        NavigationStack {
            Form {
                Section("Video") {
                    TextField("Paste Facebook, Instagram, TikTok or YouTube link", text: $urlText)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)

                    Picker("I want to", selection: $searchIntent) {
                        Text("Continue the story").tag("continue_story")
                        Text("Watch the full original").tag("full_original")
                        Text("Find the original source").tag("original_source")
                        Text("Find other copies").tag("other_copies")
                        Text("Identify what’s shown").tag("identify_shown")
                    }

                    Text(intentDescription(searchIntent))
                        .font(.caption).foregroundStyle(.secondary)

                    if let shareStatus { Text(shareStatus).font(.footnote).foregroundStyle(.secondary) }
                    Button(loading ? "Searching…" : "Find the Rest") { Task { await runSearch() } }
                        .disabled(loading || (URL(string: urlText) == nil && sharedMediaURL == nil))
                }

                if let result {
                    Section("What I found") {
                        Text(result.resultMessage.isEmpty ? resultLabel(result.resultState) : result.resultMessage)
                            .font(.headline)
                        if result.resultStateConfidence > 0 {
                            Text("State confidence: \(Int(result.resultStateConfidence * 100))%")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        if result.confidence > 0 {
                            Text("Match confidence: \(Int(result.confidence * 100))% • \(result.confidenceGrade.capitalized)")
                                .font(.caption).foregroundStyle(.secondary)
                            Text("\(result.evidenceFamilyCount) independent evidence families • \(result.strongEvidenceFamilyCount) strong")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        if result.searchCoverage.attempted > 0 {
                            Text("Search coverage: \(result.searchCoverage.completed)/\(result.searchCoverage.attempted) completed")
                                .font(.caption).foregroundStyle(.secondary)
                            if !result.searchCoverage.broadEnoughForNonpublicationHint {
                                Text("Search was incomplete, so Find the Rest will not imply that the missing continuation has not been posted.")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        if !result.availableActions.isEmpty {
                            Text(result.availableActions.map(actionLabel).joined(separator: " • "))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        if result.searchIntent == "continue_story" &&
                            (result.resultState == "likely_not_posted_yet" || result.resultState == "no_verified_match") {
                            Button(watchStatus == nil ? "Watch for the Rest" : "Check Watch Now") {
                                Task {
                                    if let watchStatus {
                                        await checkWatchNow(watchStatus.watchId)
                                    } else {
                                        await createWatchForCurrentResult()
                                    }
                                }
                            }
                            if let watchMessage {
                                Text(watchMessage).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }

                if sharedMediaURL != nil && sharedMediaKind != "image" {
                    Section("Verify a candidate clip") {
                        Button(verifyingCandidate ? "Verifying…" : "Choose Candidate Video") {
                            showingCandidatePicker = true
                        }
                        .disabled(verifyingCandidate)

                        Text("Use a candidate clip you are allowed to provide. Find the Rest compares visual, audio, story, boundary, and ephemeral appearance cues. Appearance matching does not identify or name a person.")
                            .font(.caption).foregroundStyle(.secondary)

                        if let verificationStatus {
                            Text(verificationStatus)
                                .font(.caption).foregroundStyle(.secondary)
                        }

                        if let verificationResult {
                            Text(verificationLabel(verificationResult.verdict))
                                .font(.headline)
                            Text("Verification confidence: \(Int(verificationResult.confidence * 100))%")
                            Text("Independent signals agreeing: \(verificationResult.agreementCount)")
                                .font(.caption).foregroundStyle(.secondary)

                            verificationSignalRow("Robust visual", verificationResult.robustVisualSimilarity)
                            verificationSignalRow("Audio fingerprint", verificationResult.audioFingerprintSimilarity)
                            verificationSignalRow("Boundary visual", verificationResult.boundaryVisualContinuity)
                            verificationSignalRow("Boundary audio", verificationResult.boundaryAudioContinuity)
                            verificationSignalRow("Transcript/story", verificationResult.transcriptSemantic)
                            verificationSignalRow("Scene continuity", verificationResult.sceneSemantic)
                            verificationSignalRow("Visible-person appearance", verificationResult.appearanceSimilarity)
                            verificationSignalRow("Face-region appearance", verificationResult.faceRegionSimilarity)
                            verificationSignalRow("Clothing appearance", verificationResult.clothingRegionSimilarity)

                            if verificationResult.contradictionPenalty > 0 {
                                Text("Contradiction penalty: \(Int(verificationResult.contradictionPenalty * 100))%")
                                    .font(.caption).foregroundStyle(.secondary)
                            }

                            DisclosureGroup("Signal contribution details") {
                                ForEach(verificationResult.contributions.keys.sorted(), id: \.self) { key in
                                    if let value = verificationResult.contributions[key] {
                                        HStack {
                                            Text(key.replacingOccurrences(of: "_", with: " ").capitalized)
                                            Spacer()
                                            Text("\(Int(value * 100))%")
                                                .foregroundStyle(.secondary)
                                        }
                                        .font(.caption)
                                    }
                                }
                            }

                            ForEach(verificationResult.notes, id: \.self) {
                                Text($0).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }

                if let discovery = mediaDiscovery, let best = discovery.bestMatch {
                    Section("Found from screenshot") {
                        Text(best.title).font(.headline)
                        if let creator = best.creator { Text(creator).foregroundStyle(.secondary) }
                        if let reranked = verificationRerank?.ranked.first, reranked.candidate.url == best.url {
                            Text("Verification-aware score: \(Int(reranked.adjustedScore * 100))%")
                            Text("Search score: \(Int(reranked.originalScore * 100))% • \(reranked.disposition.capitalized)")
                                .font(.caption).foregroundStyle(.secondary)
                        } else {
                            Text("Confidence: \(Int(best.score * 100))%")
                        }
                        if let url = URL(string: best.url) { Link("Open Best Match", destination: url) }
                        if let snippet = best.snippet, !snippet.isEmpty {
                            Text(snippet).font(.footnote).foregroundStyle(.secondary)
                        }
                        Text("This result was discovered from visible clues in the shared media.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if let details = best.matchedDetails, !details.isEmpty {
                        Section("Matched screenshot clues") {
                            detailRow("Names", details["names"])
                            detailRow("Phrases", details["phrases"])
                            detailRow("Numbers", details["numbers"])
                            detailRow("Keywords", details["keywords"])
                            detailRow("Handles", details["handles"])
                            detailRow("Objects", details["objects"])
                            detailRow("Logos", details["logos"])
                            detailRow("Scenes", details["scenes"])
                            detailRow("Clothing", details["clothing"])
                        }
                    }
                    if !discovery.visualObjects.isEmpty || !discovery.visualLogos.isEmpty ||
                        !discovery.visualScenes.isEmpty || !discovery.visualClothing.isEmpty {
                        Section("Visual clues") {
                            detailRow("Objects", discovery.visualObjects)
                            detailRow("Logos", discovery.visualLogos)
                            detailRow("Scenes", discovery.visualScenes)
                            detailRow("Clothing", discovery.visualClothing)
                            Text("These clues support source matching; they are not proof by themselves.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                } else if let discovery = mediaDiscovery, discovery.bestMatch == nil {
                    Section("Screenshot search") {
                        Text("No credible source or copy found from the visible clues yet.")
                        ForEach(discovery.notes, id: \.self) { Text($0).font(.footnote) }
                    }
                }

                if let best = displayBestMatch {
                    Section("Best match") {
                        Text(best.title).font(.headline)
                        if let creator = best.creator { Text(creator).foregroundStyle(.secondary) }
                        Text("Confidence: \(Int(best.score * 100))%")
                        if let role = best.traceRole {
                            Text(traceLabel(role))
                                .font(.caption).bold()
                        }
                        if let duration = best.durationSeconds, duration > 0 {
                            Text("Length: \(formatDuration(duration))").font(.caption).foregroundStyle(.secondary)
                        }
                        if let url = URL(string: best.url) { Link("Open Best Match", destination: url) }
                        if let snippet = best.snippet, !snippet.isEmpty {
                            Text(snippet).font(.footnote).foregroundStyle(.secondary)
                        }
                        Text(best.reason).font(.caption).foregroundStyle(.secondary)
                    }
                    if let details = best.matchedDetails, !details.isEmpty {
                        Section("Matched story details") {
                            detailRow("Names", details["names"])
                            detailRow("Phrases", details["phrases"])
                            detailRow("Numbers", details["numbers"])
                            detailRow("Keywords", details["keywords"])
                            detailRow("Ending clues", details["ending_terms"])
                        }
                    }
                    if let evidence = best.evidence, !evidence.isEmpty {
                        Section("Why this matched") {
                            evidenceRow("Text / topic", evidence["text_similarity"])
                            evidenceRow("Continuation wording", evidence["continuation_signal"])
                            evidenceRow("Same creator", evidence["creator_match"])
                            evidenceRow("Posting sequence", evidence["sequence_signal"])
                            evidenceRow("Visual boundary", evidence["visual_continuity"])
                            evidenceRow("Audio boundary", evidence["audio_continuity"])
                            evidenceRow("Transcript semantics", evidence["transcript_semantic"])
                            evidenceRow("Scene semantics", evidence["scene_semantic"])
                            evidenceRow("Story fingerprint", evidence["story_fingerprint"])
                            evidenceRow("Visual object/logo clues", evidence["visual_clue_match"])
                            evidenceRow("Ending continuity", evidence["ending_continuity"])
                            evidenceRow("Cliffhanger strength", evidence["cliffhanger_strength"])
                            evidenceRow("Contradiction penalty", evidence["contradiction_penalty"])
                            evidenceRow("Name conflict", evidence["name_conflict"])
                            evidenceRow("Year/number conflict", evidence["number_conflict"])
                            evidenceRow("Original-source wording", evidence["trace_textual_originality"])
                            evidenceRow("Longer/full version", evidence["trace_duration_advantage"])
                            evidenceRow("Earlier upload", evidence["trace_earlier_upload"])
                            evidenceRow("Creator authority", evidence["trace_creator_authority"])
                        }
                    }
                } else if let result {
                    Section("Result") {
                        Text("No credible continuation found yet.")
                        ForEach(result.notes, id: \.self) { Text($0).font(.footnote) }
                    }
                }
                if let result, !result.continuationChain.isEmpty {
                    Section("Story chain") {
                        Text("Chain confidence: \(Int(result.chainConfidence * 100))%")
                            .font(.caption).foregroundStyle(.secondary)
                        if !result.recoveredParts.isEmpty {
                            Text("Recovered: " + result.recoveredParts.map { "Part \($0)" }.joined(separator: ", "))
                                .font(.caption).bold()
                        }
                        if !result.missingParts.isEmpty {
                            Text("Still missing: " + result.missingParts.map { "Part \($0)" }.joined(separator: ", "))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        ForEach(result.continuationChain) { node in
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text(chainLabel(node))
                                        .font(.caption).bold()
                                    Spacer()
                                    Text("\(Int(node.chainScore * 100))%")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                                Text(node.candidate.title).font(.subheadline).bold()
                                Text(node.orderReason).font(.caption).foregroundStyle(.secondary)
                                if let url = URL(string: node.candidate.url) {
                                    Link("Open", destination: url).font(.caption)
                                }
                            }
                        }
                    }
                }

                if let graph = result?.provenanceGraph, !graph.edges.isEmpty {
                    Section("Source lineage") {
                        Text("Lineage confidence: \(Int(graph.confidence * 100))%")
                            .font(.caption).foregroundStyle(.secondary)
                        ForEach(graph.edges) { edge in
                            VStack(alignment: .leading, spacing: 4) {
                                Text("\(provenanceLabel(edge.fromId, graph)) → \(provenanceLabel(edge.toId, graph))")
                                    .font(.subheadline).bold()
                                Text(provenanceRelationship(edge.relationship))
                                    .font(.caption)
                                Text("\(Int(edge.confidence * 100))% confidence")
                                    .font(.caption).foregroundStyle(.secondary)
                                if let reason = edge.reasons.first {
                                    Text(reason)
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                        Text("Lineage is inferred from independent clues such as creator, chronology, source tracing, story overlap and repost evidence. It is not proof of authorship.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }

                if let visibleTextResult, !visibleTextResult.text.isEmpty {
                    Section("Visible clues") {
                        Text(visibleTextResult.text)
                            .font(.subheadline)
                            .textSelection(.enabled)
                        if !visibleTextResult.handles.isEmpty {
                            Text("Handles: " + visibleTextResult.handles.joined(separator: ", "))
                                .font(.caption).bold()
                        }
                        if !visibleTextResult.hashtags.isEmpty {
                            Text("Hashtags: " + visibleTextResult.hashtags.joined(separator: ", "))
                                .font(.caption)
                        }
                        if !visibleTextResult.keywords.isEmpty {
                            Text("Key clues: " + visibleTextResult.keywords.prefix(8).joined(separator: ", "))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        if !visibleTextResult.suggestedQueries.isEmpty {
                            Text("Search clues")
                                .font(.caption).bold()
                            ForEach(visibleTextResult.suggestedQueries, id: \.self) { query in
                                Text(query).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        Text("Frames examined: \(visibleTextResult.framesExamined)")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }

                if let visualResult {
                    Section("Visual fingerprint") {
                        Text(visualResult.mediaKind == "image" ? "Screenshot/image analyzed" : "Video visual fingerprint created")
                            .font(.headline)
                        Text("Representative frames: \(visualResult.representativeFrames)")
                        Text("This visual fingerprint can be used to compare reposts, alternate crops, and other copies of the same imagery.")
                            .font(.footnote).foregroundStyle(.secondary)
                        ForEach(visualResult.notes, id: \.self) { Text($0).font(.caption).foregroundStyle(.secondary) }
                    }
                }

                if let discovery = mediaDiscovery, discovery.candidates.count > 1 {
                    Section("Other screenshot candidates") {
                        ForEach(Array(discovery.candidates.dropFirst())) { candidate in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(candidate.title).font(.subheadline).bold()
                                Text("\(Int(candidate.score * 100))% • \(candidate.platform)")
                                    .font(.caption).foregroundStyle(.secondary)
                                if let snippet = candidate.snippet, !snippet.isEmpty {
                                    Text(snippet).font(.caption).foregroundStyle(.secondary)
                                }
                                if let url = URL(string: candidate.url) {
                                    Link("Open", destination: url).font(.caption)
                                }
                            }
                        }
                    }
                }

                if let result, !result.candidates.isEmpty {
                    Section("Other candidates") {
                        ForEach(result.candidates.dropFirst()) { candidate in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(candidate.title).font(.subheadline).bold()
                                Text("\(Int(candidate.score * 100))% • \(candidate.platform)\(candidate.traceRole.map { " • " + traceLabel($0) } ?? "")")
                                    .font(.caption).foregroundStyle(.secondary)
                                if let snippet = candidate.snippet, !snippet.isEmpty {
                                    Text(snippet).font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
                if currentSearchId != nil {
                    Section("Was this right?") {
                        HStack {
                            Button("Correct") { Task { await sendFeedback("correct") } }
                            Button("Wrong") { Task { await sendFeedback("wrong") } }
                            Button("Not enough") { Task { await sendFeedback("not_enough_information") } }
                        }
                        .buttonStyle(.borderless)
                        if let feedbackStatus {
                            Text(feedbackStatus).font(.caption).foregroundStyle(.secondary)
                        }
                        Text("Feedback sends coarse quality signals for regression testing—not your screenshot, video, transcript, OCR text, title, creator, or search query.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }

                if let error { Section { Text(error).foregroundStyle(.red) } }
            }
            .navigationTitle("Find the Rest")
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button("Watches", systemImage: "bell") { showingWatches = true }
                    Button("Settings", systemImage: "gearshape") { showingSettings = true }
                }
            }
            .sheet(isPresented: $showingSettings) { BackendSettingsView() }
            .sheet(isPresented: $showingWatches) { WatchManagerView() }
            .fileImporter(
                isPresented: $showingCandidatePicker,
                allowedContentTypes: [.movie],
                allowsMultipleSelection: false
            ) { result in
                switch result {
                case .success(let urls):
                    if let candidate = urls.first {
                        Task { await verifyCandidate(candidate) }
                    }
                case .failure:
                    verificationStatus = "Candidate video selection was cancelled or unavailable."
                }
            }
            .onOpenURL { url in
                guard url.scheme == "findtherest" else { return }
                consumeShareHandoff()
            }
            .task { consumeShareHandoff() }
        }
    }





    @MainActor private func createWatchForCurrentResult() async {
        guard let result else { return }
        do {
            let created = try await APIClient.shared.createWatch(sourceURL: result.sourceUrl, intent: result.searchIntent)
            watchStatus = created
            watchMessage = "Saved. Find the Rest can re-check this source later without storing the original media."
        } catch {
            watchMessage = "Could not create the watch."
        }
    }

    @MainActor private func checkWatchNow(_ watchId: String) async {
        do {
            let checked = try await APIClient.shared.checkWatch(watchId: watchId)
            watchStatus = checked.watch
            if let newResult = checked.result {
                result = newResult
            }
            watchMessage = checked.watch.message
        } catch {
            watchMessage = "Could not re-check this watch."
        }
    }


    private func provenanceLabel(_ nodeId: String, _ graph: ProvenanceGraph) -> String {
        graph.nodes.first(where: { $0.nodeId == nodeId })?.label ?? nodeId
    }

    private func provenanceRelationship(_ relationship: String) -> String {
        switch relationship {
        case "likely_source_of": return "Likely source of"
        case "continues_as": return "Continues as"
        case "continues_via_repost": return "Continuation via repost"
        case "excerpt_or_fragment": return "Excerpt or fragment"
        case "likely_repost_of": return "Likely repost of"
        case "same_creator_related": return "Same-creator related material"
        default: return relationship.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }



    @MainActor private func attemptAutomaticVerification(
        sourceURL: URL,
        candidateURL: String,
        sourceTranscript: String?
    ) async {
        do {
            let capabilities = try await APIClient.shared.capabilities()
            guard capabilities.candidateMediaVerification else { return }

            verifyingCandidate = true
            verificationStatus = "Automatically verifying the best match with permitted candidate media…"
            defer { verifyingCandidate = false }

            let candidates = Array((result?.candidates ?? []).prefix(2))
            guard !candidates.isEmpty else { return }

            let reranked = try await APIClient.shared.verifyRankedCandidates(
                sourceURL: sourceURL,
                candidates: candidates,
                sourceTranscript: sourceTranscript
            )
            verificationRerank = reranked

            if let top = reranked.ranked.first {
                verificationResult = top.verification
                if reranked.changedTopCandidate {
                    verificationStatus = "Media verification changed the leading candidate after comparing the top search results."
                } else if let verification = top.verification,
                          verification.verdict == "strong_match" || verification.verdict == "likely_match" {
                    verificationStatus = "Best match automatically verified with permitted candidate media."
                } else if top.disposition == "demote" {
                    verificationStatus = "Automatic media verification weakened the leading candidate."
                } else {
                    verificationStatus = "Automatic media verification completed; search and provenance evidence still lead the ranking."
                }
            }
        } catch {
            // Automatic verification is an enhancement. Search results remain usable if it is unavailable.
            verificationStatus = nil
        }
    }

    @MainActor private func verifyCandidate(_ candidateURL: URL) async {
        guard let sourceURL = sharedMediaURL else {
            verificationStatus = "Share a source video first."
            return
        }
        verifyingCandidate = true
        verificationResult = nil
        verificationStatus = "Comparing the source and candidate across independent media signals…"
        defer { verifyingCandidate = false }
        do {
            let verified = try await APIClient.shared.verifyMediaPair(
                sourceURL: sourceURL,
                candidateURL: candidateURL
            )
            verificationResult = verified
            verificationStatus = nil
        } catch {
            verificationStatus = "Could not verify this candidate clip: \(error.localizedDescription)"
        }
    }

    private func verificationLabel(_ verdict: String) -> String {
        switch verdict {
        case "strong_match": return "Strong media match"
        case "likely_match": return "Likely media match"
        case "possible_match": return "Possible media match"
        default: return "Candidate not verified"
        }
    }

    @ViewBuilder private func verificationSignalRow(_ label: String, _ value: Double) -> some View {
        HStack {
            Text(label)
            Spacer()
            Text("\(Int(value * 100))%")
                .foregroundStyle(.secondary)
        }
        .font(.caption)
    }


    private func intentDescription(_ intent: String) -> String {
        switch intent {
        case "full_original": return "Prefer longer, complete or uncut versions over segmented clips."
        case "original_source": return "Prefer provenance, earlier uploads and creator authority."
        case "other_copies": return "Prefer reposts, mirrors and alternate copies of the same material."
        case "identify_shown": return "Prefer candidates that explain the strongest visible and story clues."
        default: return "Prefer the most credible next part or continuation."
        }
    }

    private func resultLabel(_ state: String) -> String {
        switch state {
        case "continuation_found": return "Credible continuation found."
        case "full_original_found": return "Likely full/original found."
        case "original_source_found": return "Credible original-source candidate found."
        case "copies_found": return "Credible alternate copy or repost found."
        case "identification_found": return "Credible source or context match found."
        case "related_only": return "Related material found, but the selected goal is not verified yet."
        case "likely_not_posted_yet": return "The continuation may not have been posted yet."
        case "insufficient_context": return "Not enough context to verify the selected goal."
        case "no_verified_full_original": return "No verified full/original version found."
        case "no_verified_source": return "No verified original source found."
        case "no_verified_copy": return "No verified alternate copy found."
        case "no_verified_identification": return "No verified identification found."
        default: return "No verified match found."
        }
    }

    private func actionLabel(_ action: String) -> String {
        switch action {
        case "watch_continuation": return "Watch continuation"
        case "watch_full_original": return "Watch full original"
        case "find_continuation": return "Find continuation"
        case "find_full_original": return "Find full original"
        case "find_other_copies": return "Find other copies"
        case "find_original_source": return "Find original source"
        case "open_original_source": return "Open original source"
        case "open_full_original": return "Open full/original"
        case "open_copy": return "Open copy"
        case "open_identification": return "Open match"
        case "review_related": return "Review related"
        case "check_later": return "Check later"
        case "share_media": return "Share video"
        case "share_screenshot": return "Share screenshot"
        case "try_source_link": return "Try source link"
        default: return action.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private var currentSearchId: String? {
        mediaDiscovery?.searchId ?? result?.searchId
    }

    private var displayBestMatch: Candidate? {
        verificationRerank?.ranked.first?.candidate ?? result?.bestMatch
    }

    private var currentBestMatchURL: String? {
        mediaDiscovery?.bestMatch?.url ?? displayBestMatch?.url
    }

    private var currentConfidence: Double? {
        if let discovery = mediaDiscovery { return discovery.confidence }
        return result?.confidence
    }

    private var currentSourcePlatform: String? {
        result?.sourcePlatform
    }

    private var currentSearchIntent: String {
        result?.searchIntent ?? searchIntent
    }

    private var currentResultState: String? {
        result?.resultState
    }

    private var currentConfidenceGrade: String {
        result?.confidenceGrade ?? "low"
    }

    private var currentEvidenceFamilyCount: Int {
        result?.evidenceFamilyCount ?? 0
    }

    private var currentStrongEvidenceFamilyCount: Int {
        result?.strongEvidenceFamilyCount ?? 0
    }

    @MainActor private func sendFeedback(_ verdict: String) async {
        guard let searchId = currentSearchId else { return }
        do {
            let response = try await APIClient.shared.submitFeedback(FeedbackRequest(
                searchId: searchId,
                verdict: verdict,
                bestMatchUrl: currentBestMatchURL,
                sourcePlatform: currentSourcePlatform,
                confidence: currentConfidence,
                searchIntent: currentSearchIntent,
                resultState: currentResultState,
                confidenceGrade: currentConfidenceGrade,
                evidenceFamilyCount: currentEvidenceFamilyCount,
                strongEvidenceFamilyCount: currentStrongEvidenceFamilyCount
            ))
            feedbackStatus = response.accepted ? "Thanks — feedback recorded." : "Feedback was not accepted."
        } catch {
            feedbackStatus = "Could not send feedback."
        }
    }

    private func chainLabel(_ node: ChainNode) -> String {
        if let part = node.inferredPart { return "Part \(part)" }
        if let episode = node.episodeNumber { return "Episode \(episode)" }
        switch node.relationship {
        case "full_original": return "Full/original"
        case "update": return "Update"
        case "continuation": return "Continuation"
        default: return "Related"
        }
    }

    private func traceLabel(_ role: String) -> String {
        switch role {
        case "likely_original": return "Likely full/original source"
        case "fragment": return "Likely fragment"
        case "likely_repost": return "Likely repost"
        default: return "Related"
        }
    }

    private func formatDuration(_ seconds: Double) -> String {
        let total = Int(seconds.rounded())
        let h = total / 3600
        let m = (total % 3600) / 60
        let s = total % 60
        return h > 0 ? String(format: "%d:%02d:%02d", h, m, s) : String(format: "%d:%02d", m, s)
    }

    @ViewBuilder private func detailRow(_ label: String, _ values: [String]?) -> some View {
        if let values, !values.isEmpty {
            VStack(alignment: .leading, spacing: 2) {
                Text(label).font(.caption).bold()
                Text(values.joined(separator: ", "))
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder private func evidenceRow(_ label: String, _ value: Double?) -> some View {
        if let value { HStack { Text(label); Spacer(); Text("\(Int(value * 100))%").foregroundStyle(.secondary) } }
    }

    @MainActor private func runSearch() async {
        let url = URL(string: urlText)
        loading = true; error = nil
        watchStatus = nil; watchMessage = nil
        verificationResult = nil; verificationRerank = nil; verificationStatus = nil
        lastLocalTranscript = nil
        defer { loading = false }
        do {
            if let mediaURL = sharedMediaURL, let url {
                let clues = await LocalMediaClueExtractor.extract(from: mediaURL, mediaKind: sharedMediaKind)
                lastLocalTranscript = clues.transcript
                mediaDiscovery = nil

                if clues.visibleText != nil || clues.transcript != nil {
                    result = try await APIClient.shared.analyzeWithLocalClues(
                        url: url,
                        intent: searchIntent,
                        transcript: clues.transcript,
                        visibleText: clues.visibleText
                    )
                    let parts = [
                        clues.visibleText != nil ? "visible text" : nil,
                        clues.transcript != nil ? "speech" : nil
                    ].compactMap { $0 }
                    shareStatus = "Analyzed \(parts.joined(separator: " + ")) on this iPhone; source media was not uploaded."
                } else {
                    result = try await APIClient.shared.analyzeShared(url: url, mediaURL: mediaURL, intent: searchIntent)
                    shareStatus = "No usable on-device text clues were found, so permitted source media was sent for temporary backend analysis."
                }
            } else if let mediaURL = sharedMediaURL, sharedMediaKind == "image" {
                // A screenshot with no source URL still needs provider-assisted discovery.
                mediaDiscovery = try await APIClient.shared.discoverMedia(mediaURL: mediaURL)
                result = nil
                shareStatus = "Standalone screenshot searched using the configured discovery providers."
            } else if let url {
                mediaDiscovery = nil
                result = try await APIClient.shared.analyze(url: url, intent: searchIntent)
            } else {
                throw URLError(.badURL)
            }

            if let result,
               let mediaURL = sharedMediaURL,
               sharedMediaKind != "image",
               let best = result.bestMatch {
                await attemptAutomaticVerification(
                    sourceURL: mediaURL,
                    candidateURL: best.url,
                    sourceTranscript: lastLocalTranscript
                )
            }
        } catch { self.error = error.localizedDescription }
    }

    @MainActor private func consumeShareHandoff() {
        guard let handoff = ShareHandoff.consume() else { return }
        if let u = handoff.payload.url { urlText = u }
        sharedMediaURL = handoff.mediaURL
        sharedMediaKind = handoff.payload.mediaKind
        if handoff.mediaURL == nil {
            shareStatus = "Shared link received."
        } else if handoff.payload.mediaKind == "image" {
            shareStatus = "Shared screenshot/image received for visual analysis."
        } else {
            shareStatus = "Shared video received for permitted media analysis."
        }
        Task { await runSearch() }
    }
}


private struct WatchManagerView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var watches: [WatchStatusResponse] = []
    @State private var loading = false
    @State private var status: String?

    var body: some View {
        NavigationStack {
            List {
                if watches.isEmpty && !loading {
                    ContentUnavailableView(
                        "No Active Watches",
                        systemImage: "bell.slash",
                        description: Text("Use “Watch for the Rest” after an unresolved search.")
                    )
                } else {
                    ForEach(watches, id: \.watchId) { watch in
                        VStack(alignment: .leading, spacing: 7) {
                            Text(watch.sourceUrl)
                                .font(.subheadline)
                                .lineLimit(2)
                            Text("Goal: " + watch.intent.replacingOccurrences(of: "_", with: " ").capitalized)
                                .font(.caption).foregroundStyle(.secondary)
                            if let state = watch.lastResultState {
                                Text(state.replacingOccurrences(of: "_", with: " ").capitalized)
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            HStack {
                                Button("Check Now") { Task { await check(watch.watchId) } }
                                Button("Remove", role: .destructive) { Task { await remove(watch.watchId) } }
                            }
                            .buttonStyle(.borderless)
                        }
                    }
                }
                if let status {
                    Section { Text(status).font(.caption).foregroundStyle(.secondary) }
                }
            }
            .navigationTitle("Watches")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
                ToolbarItem(placement: .topBarLeading) {
                    Button("Refresh", systemImage: "arrow.clockwise") { Task { await load() } }
                }
            }
            .task { await load() }
            .refreshable { await load() }
        }
    }

    @MainActor private func load() async {
        loading = true
        defer { loading = false }
        do {
            watches = try await APIClient.shared.listWatches().watches
            status = nil
        } catch {
            status = "Could not load watches."
        }
    }

    @MainActor private func check(_ watchId: String) async {
        do {
            let response = try await APIClient.shared.checkWatch(watchId: watchId)
            status = response.watch.message
            await load()
        } catch {
            status = "Could not check this watch."
        }
    }

    @MainActor private func remove(_ watchId: String) async {
        do {
            let response = try await APIClient.shared.removeWatch(watchId: watchId)
            status = response.message
            watches.removeAll { $0.watchId == watchId }
        } catch {
            status = "Could not remove this watch."
        }
    }
}

private struct BackendSettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var backendURL = APIClient.shared.configuredBaseURLString
    @State private var status: String?
    @State private var testing = false
    @State private var apiKey = APIClient.shared.configuredAPIKey
    @State private var capabilities: CapabilitiesResponse?
    @State private var capabilitiesStatus: String?
    @State private var loadingCapabilities = false
    @State private var betaReadiness: BetaReadinessResponse?
    @State private var loadingReadiness = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Backend") {
                    TextField("https://your-service.example", text: $backendURL)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                    SecureField("API key (if configured on server)", text: $apiKey)
                        .textInputAutocapitalization(.never)
                    Text("Find the Rest requires an HTTPS backend on a physical iPhone. The API key protects beta endpoints from public use.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Section {
                    Button(testing ? "Testing…" : "Save & Test Connection") {
                        Task { await saveAndTest() }
                    }.disabled(testing)
                    if let status { Text(status).font(.footnote) }
                }

                Section("Release readiness") {
                    if let readiness = betaReadiness {
                        HStack {
                            Image(systemName: readiness.betaReady ? "checkmark.seal.fill" : "exclamationmark.triangle.fill")
                                .accessibilityHidden(true)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(readiness.betaReady ? "Core beta gates passed" : "Not ready for beta deployment")
                                    .font(.headline)
                                Text("\(readiness.criticalPassed)/\(readiness.criticalTotal) critical • \(readiness.passed)/\(readiness.total) total checks")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        ForEach(readiness.gates) { gate in
                            VStack(alignment: .leading, spacing: 3) {
                                HStack {
                                    Image(systemName: gate.passed ? "checkmark.circle.fill" : (gate.critical ? "xmark.octagon.fill" : "circle.dashed"))
                                        .accessibilityHidden(true)
                                    Text(gate.label)
                                    Spacer()
                                    if gate.critical {
                                        Text("Required").font(.caption2).foregroundStyle(.secondary)
                                    }
                                }
                                Text(gate.detail).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        Text("This checks configuration and deterministic safeguards; real-device/TestFlight testing is still required.")
                            .font(.caption).foregroundStyle(.secondary)
                    } else {
                        Text("Run the release check after connecting the backend.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }

                    Button(loadingReadiness ? "Checking…" : "Run Release Check") {
                        Task { await loadReadiness() }
                    }
                    .disabled(loadingReadiness)
                }

                Section("Backend capabilities") {
                    if let capabilities {
                        capabilityRow("YouTube search", capabilities.youtubeSearch, "Requires a YouTube Data API key.")
                        capabilityRow("Open-web search", capabilities.openWebSearch, "Enables cross-platform public-web discovery.")
                        capabilityRow("Reverse-image search", capabilities.reverseImageSearch, "Requires the configured visual-search gateway.")
                        capabilityRow("Automatic media verification", capabilities.candidateMediaVerification, "Uses a licensed/permitted candidate-media gateway; Find the Rest never directly downloads arbitrary social URLs.")
                        capabilityRow("Local transcription", capabilities.localTranscription, "Enables spoken-story fingerprints on the backend.")
                        capabilityRow("Continuation watches", capabilities.watchStore, "Watch storage and re-checks are available.")
                        if capabilities.watchStore {
                            Text("Watch storage: " + capabilities.watchStorageBackend.uppercased())
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        capabilityRow("Feedback capture", capabilities.feedbackStore, "Correct/Wrong/Not enough feedback can be recorded.")
                        capabilityRow("Push notifications", capabilities.pushNotifications, "Requires the configured APNs push gateway.")
                        ForEach(capabilities.notes, id: \.self) {
                            Text($0).font(.caption).foregroundStyle(.secondary)
                        }
                    } else {
                        Text(capabilitiesStatus ?? "Connect to the backend to see which beta services are enabled.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }

                    Button(loadingCapabilities ? "Refreshing…" : "Refresh Capabilities") {
                        Task { await loadCapabilities() }
                    }
                    .disabled(loadingCapabilities)
                }
            }
            .navigationTitle("Settings")
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .task {
                if !APIClient.shared.configuredBaseURLString.isEmpty {
                    await loadCapabilities()
                }
            }
        }
    }


    @ViewBuilder private func capabilityRow(_ label: String, _ enabled: Bool, _ explanation: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Image(systemName: enabled ? "checkmark.circle.fill" : "circle.dashed")
                    .accessibilityHidden(true)
                Text(label)
                Spacer()
                Text(enabled ? "Enabled" : "Not configured")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Text(enabled ? explanation.replacingOccurrences(of: "Requires ", with: "Using ") : explanation)
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    @MainActor private func loadCapabilities() async {
        loadingCapabilities = true
        capabilitiesStatus = nil
        defer { loadingCapabilities = false }
        do {
            capabilities = try await APIClient.shared.capabilities()
        } catch {
            capabilities = nil
            capabilitiesStatus = "Could not read backend capabilities. Check the URL/API key and try again."
        }
    }

    @MainActor private func loadReadiness() async {
        loadingReadiness = true
        defer { loadingReadiness = false }
        do {
            betaReadiness = try await APIClient.shared.betaReadiness()
        } catch {
            betaReadiness = nil
            status = error.localizedDescription
        }
    }

    @MainActor private func saveAndTest() async {
        testing = true; defer { testing = false }
        do {
            try APIClient.shared.setBaseURL(backendURL)
            APIClient.shared.setAPIKey(apiKey)
            let healthy = try await APIClient.shared.health()
            status = healthy ? "Connected successfully." : "Server responded, but health check failed."
            if healthy {
                await loadCapabilities()
                await loadReadiness()
            }
        } catch {
            capabilities = nil
            status = error.localizedDescription
        }
    }
}
