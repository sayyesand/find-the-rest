import Foundation
import Vision
import AVFoundation
import Speech
import UIKit

struct LocalMediaClues {
    let visibleText: String?
    let transcript: String?
    let ocrFrames: Int
    let speechAvailable: Bool
}

enum LocalMediaClueExtractor {
    static func extract(from url: URL, mediaKind: String?) async -> LocalMediaClues {
        async let ocr = extractVisibleText(from: url, mediaKind: mediaKind)
        async let speech = transcribeVideoIfAvailable(url, mediaKind: mediaKind)
        let (ocrResult, speechResult) = await (ocr, speech)
        return LocalMediaClues(
            visibleText: ocrResult.text,
            transcript: speechResult.text,
            ocrFrames: ocrResult.frames,
            speechAvailable: speechResult.available
        )
    }

    private static func extractVisibleText(from url: URL, mediaKind: String?) async -> (text: String?, frames: Int) {
        let access = url.startAccessingSecurityScopedResource()
        defer { if access { url.stopAccessingSecurityScopedResource() } }

        if mediaKind == "image" {
            guard let image = UIImage(contentsOfFile: url.path)?.cgImage else { return (nil, 0) }
            let text = recognize(image)
            return (text.isEmpty ? nil : text, 1)
        }

        let asset = AVURLAsset(url: url)
        do {
            let duration = try await asset.load(.duration)
            let seconds = max(0.1, CMTimeGetSeconds(duration))
            let positions = [0.15, 0.50, 0.85]
            let generator = AVAssetImageGenerator(asset: asset)
            generator.appliesPreferredTrackTransform = true
            generator.requestedTimeToleranceBefore = .zero
            generator.requestedTimeToleranceAfter = .zero

            var chunks: [String] = []
            var examined = 0
            for position in positions {
                let time = CMTime(seconds: seconds * position, preferredTimescale: 600)
                if let cg = try? generator.copyCGImage(at: time, actualTime: nil) {
                    examined += 1
                    let found = recognize(cg)
                    if !found.isEmpty && !chunks.contains(found) {
                        chunks.append(found)
                    }
                }
            }
            let merged = chunks.joined(separator: "\n")
            return (merged.isEmpty ? nil : merged, examined)
        } catch {
            return (nil, 0)
        }
    }

    private static func recognize(_ image: CGImage) -> String {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true
        request.minimumTextHeight = 0.015
        let handler = VNImageRequestHandler(cgImage: image, options: [:])
        do {
            try handler.perform([request])
            let strings = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
            var seen = Set<String>()
            return strings.filter {
                let key = $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                guard !key.isEmpty, !seen.contains(key) else { return false }
                seen.insert(key)
                return true
            }.joined(separator: "\n")
        } catch {
            return ""
        }
    }

    private static func transcribeVideoIfAvailable(_ url: URL, mediaKind: String?) async -> (text: String?, available: Bool) {
        guard mediaKind != "image" else { return (nil, false) }
        let access = url.startAccessingSecurityScopedResource()
        defer { if access { url.stopAccessingSecurityScopedResource() } }
        let authorization = await speechAuthorization()
        guard authorization == .authorized else { return (nil, false) }
        guard let recognizer = SFSpeechRecognizer(), recognizer.isAvailable else { return (nil, false) }

        return await withCheckedContinuation { continuation in
            let request = SFSpeechURLRecognitionRequest(url: url)
            request.shouldReportPartialResults = false
            if #available(iOS 16.0, *) {
                request.addsPunctuation = true
            }
            var resumed = false
            let task = recognizer.recognitionTask(with: request) { result, error in
                guard !resumed else { return }
                if let result, result.isFinal {
                    resumed = true
                    continuation.resume(returning: (
                        result.bestTranscription.formattedString.isEmpty ? nil : result.bestTranscription.formattedString,
                        true
                    ))
                } else if error != nil {
                    resumed = true
                    continuation.resume(returning: (nil, true))
                }
            }
            DispatchQueue.global().asyncAfter(deadline: .now() + 20) {
                guard !resumed else { return }
                resumed = true
                task.cancel()
                continuation.resume(returning: (nil, true))
            }
        }
    }

    private static func speechAuthorization() async -> SFSpeechRecognizerAuthorizationStatus {
        let current = SFSpeechRecognizer.authorizationStatus()
        if current != .notDetermined { return current }
        return await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { status in
                continuation.resume(returning: status)
            }
        }
    }
}
