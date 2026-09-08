import os
import shutil
import tempfile
import json
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from dotenv import load_dotenv

from .media import compare_media
from .semantic import compare_semantics, transcribe_media
from .models import AnalyzeRequest, LocalClueAnalyzeRequest, AnalyzeResponse, MediaCompareResponse, SemanticCompareResponse, ChainVerifyResponse, ChainLinkVerification, VisualFingerprintResponse, VisualCompareResponse, VisibleTextResponse, MediaDiscoveryResponse, VisualCluesResponse, FeedbackRequest, FeedbackResponse, FeedbackSummaryResponse, WatchCreateRequest, WatchStatusResponse, WatchCheckResponse, WatchListResponse, CapabilitiesResponse, WatchDeleteResponse, RobustVisualCompareResponse, AudioFingerprintCompareResponse, MultimodalVerifyResponse, WatchBatchCheckResponse, WatchBatchCheckItem, PushRegisterRequest, PushRegisterResponse, PushUnregisterResponse, DiagnosticsSummaryResponse, BenchmarkSummaryResponse, CandidateURLVerifyResponse, Candidate, VerificationRerankResponse, VerificationRankedCandidateResponse, AppearanceCompareResponse, BetaReadinessResponse
from .service import analyze
from .outcome import is_success_state
from .platforms import detect_platform
from .chain_verify import verify_link, chain_confidence
from .visual import fingerprint_media, visual_similarity, robust_media_similarity
from .appearance import compare_appearance
from .audio_fingerprint import fingerprint_audio, audio_fingerprint_similarity
from .multimodal_verify import VerificationSignals, fuse_verification
from .visible_text import extract_visible_text, visible_text_queries
from .media_discovery import discover_from_visible_text, discover_from_media
from .vision_clues import extract_visual_clues, clue_queries
from .cache import canonical_key, get as cache_get, put as cache_put, stats as cache_stats
from .feedback import record_feedback
from .feedback_cases import record_case as record_feedback_case, summary as feedback_case_summary
from .watch_store import create_watch, get_watch, update_watch, list_active, deactivate_watch, list_due, storage_info
from .push import register_device, unregister_device, send_found_notification
from .diagnostics import record_event, summary as diagnostics_summary, timer as DiagnosticsTimer
from .benchmark import benchmark_summary
from .beta_readiness import readiness_summary
from .candidate_media import fetch_permitted_candidate_media, configured as candidate_media_configured
from .verification_rank import rerank_verified_candidates
import secrets
from datetime import datetime, timezone

load_dotenv()
app = FastAPI(title="Find the Rest API", version="0.55.0")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

if WEB_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIR)), name="web-assets")

_cors_origins = [x.strip() for x in os.getenv("FINDREST_CORS_ORIGINS", "").split(",") if x.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-FindTheRest-Key"],
    )

_trusted_hosts = [x.strip() for x in os.getenv("FINDREST_TRUSTED_HOSTS", "").split(",") if x.strip()]
if _trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_trusted_hosts)

MAX_MEDIA_BYTES = 60 * 1024 * 1024
ALLOWED_MEDIA_TYPES = {"video/mp4", "video/quicktime", "video/x-m4v", "image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "application/octet-stream"}

@app.get("/", include_in_schema=False)
async def web_home():
    index = WEB_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Web app is not installed")
    return FileResponse(index)

@app.get("/manifest.webmanifest", include_in_schema=False)
async def web_manifest():
    return FileResponse(WEB_DIR / "manifest.webmanifest", media_type="application/manifest+json")

def require_api_key(x_findtherest_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("FIND_THE_REST_API_KEY", "").strip()
    if expected and x_findtherest_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

def _validate_upload(upload: UploadFile) -> None:
    if upload.content_type and upload.content_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported media type: {upload.content_type}")

@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": "find-the-rest",
        "version": "0.55.0",
        "privacy": "uploaded media is processed in temporary request directories and discarded",
    }

@app.post("/v1/analyze", response_model=AnalyzeResponse, dependencies=[Depends(require_api_key)])
async def analyze_url(req: AnalyzeRequest):
    clock = DiagnosticsTimer()
    key = canonical_key("analyze", f"{req.scope}|{str(req.url)}")
    cached = cache_get(key)
    if cached is not None:
        notes = list(cached.notes)
        notes.append("Returned from short-lived result cache.")
        result = cached.model_copy(update={"notes": notes})
        record_event(
            "analyze",
            success=True,
            cached=True,
            latency_ms=round(clock.ms, 1),
            source_platform=result.source_platform,
            result_state=result.result_state,
            confidence=round(result.confidence, 4),
            candidate_count=len(result.candidates),
            evidence_paths=["cache"],
        )
        return result
    try:
        response = await analyze(req)
        cache_put(key, response)
        evidence_paths = []
        if any(c.evidence.get("story_fingerprint", 0) > 0 for c in response.candidates):
            evidence_paths.append("story_fingerprint")
        if any(c.evidence.get("ending_continuity", 0) > 0 for c in response.candidates):
            evidence_paths.append("ending")
        if any(c.evidence.get("trace_textual_originality", 0) > 0 for c in response.candidates):
            evidence_paths.append("source_trace")
        if response.provenance_graph and response.provenance_graph.edges:
            evidence_paths.append("provenance")
        record_event(
            "analyze",
            success=True,
            cached=False,
            latency_ms=round(clock.ms, 1),
            source_platform=response.source_platform,
            result_state=response.result_state,
            confidence=round(response.confidence, 4),
            candidate_count=len(response.candidates),
            search_attempted=response.search_coverage.attempted,
            search_completed=response.search_coverage.completed,
            search_failed=response.search_coverage.failed,
            search_coverage_ratio=response.search_coverage.coverage_ratio,
            broad_search_coverage=response.search_coverage.broad_enough_for_nonpublication_hint,
            evidence_paths=evidence_paths,
        )
        return response
    except Exception:
        record_event(
            "analyze",
            success=False,
            cached=False,
            latency_ms=round(clock.ms, 1),
            source_platform=detect_platform(str(req.url)),
        )
        raise

async def _save_upload(upload: UploadFile, dest: Path) -> None:
    total = 0
    with dest.open("wb") as f:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_MEDIA_BYTES:
                raise HTTPException(status_code=413, detail="Media clip exceeds 60 MB limit")
            f.write(chunk)




@app.post("/v1/analyze-clues", response_model=AnalyzeResponse, dependencies=[Depends(require_api_key)])
async def analyze_local_clues(req: LocalClueAnalyzeRequest):
    """Analyze a source URL using text clues extracted on the user's device.

    The transcript/OCR text is request-scoped and is not written to the diagnostics,
    feedback, watch, or cache stores.
    """
    clock = DiagnosticsTimer()
    base = AnalyzeRequest(url=req.url, scope=req.scope, intent=req.intent)
    try:
        response = await analyze(
            base,
            source_transcript=(req.transcript or "").strip() or None,
            source_visible_text=(req.visible_text or "").strip() or None,
        )
        paths = ["on_device_clues"]
        if req.transcript:
            paths.append("on_device_transcript")
        if req.visible_text:
            paths.append("on_device_ocr")
        record_event(
            "analyze_local_clues",
            success=True,
            latency_ms=round(clock.ms, 1),
            source_platform=response.source_platform,
            result_state=response.result_state,
            confidence=round(response.confidence, 4),
            candidate_count=len(response.candidates),
            evidence_paths=paths,
        )
        notes = list(response.notes)
        notes.append("On-device text clues were used; the source media itself did not need to be uploaded for this analysis.")
        return response.model_copy(update={"notes": notes})
    except Exception:
        record_event(
            "analyze_local_clues",
            success=False,
            latency_ms=round(clock.ms, 1),
            source_platform=detect_platform(str(req.url)),
        )
        raise


@app.post("/v1/share-analyze", response_model=AnalyzeResponse, dependencies=[Depends(require_api_key)])
async def analyze_shared_video(
    url: str | None = Form(default=None),
    scope: str = Form(default="web"),
    intent: str = Form(default="continue_story"),
    source: UploadFile | None = File(default=None),
    source_transcript: str | None = Form(default=None),
):
    """Analyze a URL from the iOS Share Extension. If the source app supplies the
    movie, Find the Rest may transcribe that user-shared media locally (when enabled)
    and use the spoken story to fingerprint/search. Media is discarded after request.
    """
    if not url and source is None:
        raise HTTPException(status_code=400, detail="Share must include a URL or movie")
    if not url:
        raise HTTPException(status_code=422, detail="A post URL is currently required for candidate discovery")
    if scope not in {"creator", "social", "web"}:
        raise HTTPException(status_code=422, detail="Invalid search scope")
    if intent not in {"continue_story","full_original","original_source","other_copies","identify_shown"}:
        raise HTTPException(status_code=422, detail="Invalid search intent")

    transcript = (source_transcript or "").strip() or None
    transcript_backend = "provided" if transcript else None
    media_received = False

    if source is not None:
        _validate_upload(source)
        suffix = Path(source.filename or "source.mp4").suffix or ".mp4"
        with tempfile.TemporaryDirectory(prefix="findrest-share-") as td:
            sp = Path(td) / f"source{suffix}"
            await _save_upload(source, sp)
            if not sp.exists() or sp.stat().st_size == 0:
                raise HTTPException(status_code=422, detail="Shared movie was empty")
            media_received = True
            is_image = bool(source.content_type and source.content_type.startswith("image/"))
            visible_ev = extract_visible_text(str(sp))
            visible_text = visible_ev.text or None
            if not is_image and not transcript:
                transcript, transcript_backend = transcribe_media(str(sp))
            req = AnalyzeRequest(url=url, scope=scope, intent=intent)
            response = await analyze(req, source_transcript=transcript, source_visible_text=visible_text)
    else:
        req = AnalyzeRequest(url=url, scope=scope, intent=intent)
        response = await analyze(req, source_transcript=transcript)

    notes = list(response.notes)
    if media_received:
        notes.append("Shared source media was received successfully and discarded after analysis.")
        if transcript:
            notes.append(f"Spoken-story transcription was used for fingerprinting ({transcript_backend}).")
        else:
            notes.append(f"No source transcript was available ({transcript_backend or 'transcription not enabled'}).")
        if visible_text:
            notes.append(f"Visible-text OCR contributed {len(visible_ev.keywords)} keyword clue(s) from {visible_ev.frames_examined} frame(s).")
        notes.append("Candidate media is never scraped from restricted platforms.")
    else:
        notes.append("Shared link received; no movie file was supplied by the source app.")

    return response.model_copy(update={"notes": notes})

@app.post("/v1/compare-media", response_model=MediaCompareResponse, dependencies=[Depends(require_api_key)])
async def compare_media_files(
    source: UploadFile = File(..., description="Source/Part 1 clip or exported video"),
    candidate: UploadFile = File(..., description="Candidate continuation clip or exported video"),
):
    # This endpoint intentionally accepts user-provided/permitted media rather than scraping platforms.
    _validate_upload(source)
    _validate_upload(candidate)
    source_suffix = Path(source.filename or "source.mp4").suffix or ".mp4"
    candidate_suffix = Path(candidate.filename or "candidate.mp4").suffix or ".mp4"
    with tempfile.TemporaryDirectory(prefix="findrest-") as td:
        sp = Path(td) / f"source{source_suffix}"
        cp = Path(td) / f"candidate{candidate_suffix}"
        await _save_upload(source, sp)
        await _save_upload(candidate, cp)
        try:
            ev = compare_media(str(sp), str(cp))
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=f"Could not decode supplied media: {exc}")

    combined = min(0.99, ev.visual * 0.60 + ev.audio * 0.40)
    notes = [
        "Visual score compares the final source frames with the opening candidate frames.",
        "Audio score compares boundary waveform continuity when an audio track is present.",
        "A production ranking should combine these scores with creator, timing, title/description and transcript evidence.",
    ]
    return MediaCompareResponse(
        visual_continuity=round(ev.visual, 4),
        audio_continuity=round(ev.audio, 4),
        combined_media_confidence=round(combined, 4),
        visual_frames_compared=ev.visual_frames,
        audio_samples_compared=ev.audio_samples,
        notes=notes,
    )


@app.post("/v1/compare-semantic", response_model=SemanticCompareResponse, dependencies=[Depends(require_api_key)])
async def compare_semantic_files(
    source: UploadFile = File(..., description="Source/Part 1 clip"),
    candidate: UploadFile = File(..., description="Candidate continuation clip"),
    source_transcript: str | None = Form(default=None),
    candidate_transcript: str | None = Form(default=None),
):
    _validate_upload(source)
    _validate_upload(candidate)
    source_suffix = Path(source.filename or "source.mp4").suffix or ".mp4"
    candidate_suffix = Path(candidate.filename or "candidate.mp4").suffix or ".mp4"
    with tempfile.TemporaryDirectory(prefix="findrest-semantic-") as td:
        sp = Path(td) / f"source{source_suffix}"
        cp = Path(td) / f"candidate{candidate_suffix}"
        await _save_upload(source, sp)
        await _save_upload(candidate, cp)
        try:
            ev = compare_semantics(
                str(sp), str(cp),
                source_transcript=source_transcript,
                candidate_transcript=candidate_transcript,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=f"Could not decode supplied media: {exc}")

    combined = min(0.99, ev.transcript * 0.58 + ev.scene * 0.42)
    notes = [
        "Transcript continuity measures whether the candidate continues the same concepts/story, not merely identical words.",
        "Scene continuity uses a compact visual embedding over several ending/opening frames, making it less brittle than exact frame matching.",
        "Local speech transcription is optional and disabled by default; callers may provide transcripts directly.",
    ]
    return SemanticCompareResponse(
        transcript_semantic=round(ev.transcript, 4),
        scene_semantic=round(ev.scene, 4),
        combined_semantic_confidence=round(combined, 4),
        transcript_backend=ev.transcript_backend,
        source_transcript=ev.source_transcript,
        candidate_transcript=ev.candidate_transcript,
        scene_frames_compared=ev.scene_frames,
        notes=notes,
    )


@app.post("/v1/verify-chain", response_model=ChainVerifyResponse, dependencies=[Depends(require_api_key)])
async def verify_chain_files(
    clips: list[UploadFile] = File(..., description="Ordered permitted clips: source, Part 2, Part 3, etc."),
):
    if len(clips) < 2:
        raise HTTPException(status_code=422, detail="At least two ordered clips are required")
    if len(clips) > 6:
        raise HTTPException(status_code=422, detail="Chain verification accepts at most six clips per request")
    for clip in clips:
        _validate_upload(clip)

    with tempfile.TemporaryDirectory(prefix="findrest-chain-") as td:
        paths: list[Path] = []
        names: list[str] = []
        for i, clip in enumerate(clips):
            suffix = Path(clip.filename or f"clip-{i+1}.mp4").suffix or ".mp4"
            path = Path(td) / f"{i:02d}{suffix}"
            await _save_upload(clip, path)
            if not path.exists() or path.stat().st_size == 0:
                raise HTTPException(status_code=422, detail=f"Clip {i+1} was empty")
            paths.append(path)
            names.append(clip.filename or f"Clip {i+1}")

        links = []
        raw_links = []
        try:
            for i in range(len(paths) - 1):
                ev = verify_link(str(paths[i]), str(paths[i+1]))
                raw_links.append(ev)
                links.append(ChainLinkVerification(
                    from_index=i,
                    to_index=i+1,
                    from_name=names[i],
                    to_name=names[i+1],
                    visual_continuity=round(ev.visual, 4),
                    audio_continuity=round(ev.audio, 4),
                    transcript_semantic=round(ev.transcript, 4),
                    scene_semantic=round(ev.scene, 4),
                    link_confidence=round(ev.confidence, 4),
                    verified=ev.verified,
                    notes=[
                        "Compares the ending of the earlier clip with the beginning of the next clip.",
                        "Verification uses only the user-provided/permitted clips in this request.",
                    ],
                ))
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=f"Could not decode supplied chain media: {exc}")

    overall = chain_confidence(raw_links)
    verified_count = sum(1 for x in raw_links if x.verified)
    return ChainVerifyResponse(
        links=links,
        overall_chain_confidence=round(overall, 4),
        verified_links=verified_count,
        total_links=len(raw_links),
        notes=[
            "Overall confidence weights the weakest transition heavily so one bad link cannot hide inside a strong chain.",
            "This endpoint never downloads candidate clips from social platforms; clips must be supplied by the user or another permitted source.",
        ],
    )


@app.post("/v1/visual-fingerprint", response_model=VisualFingerprintResponse, dependencies=[Depends(require_api_key)])
async def visual_fingerprint_file(
    media: UploadFile = File(..., description="User-provided/permitted image, screenshot, or video"),
):
    _validate_upload(media)
    suffix = Path(media.filename or "visual.bin").suffix or ".bin"
    with tempfile.TemporaryDirectory(prefix="findrest-visual-") as td:
        path = Path(td) / f"source{suffix}"
        await _save_upload(media, path)
        if not path.exists() or path.stat().st_size == 0:
            raise HTTPException(status_code=422, detail="Visual media was empty")
        try:
            fp = fingerprint_media(str(path))
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=f"Could not decode supplied visual media: {exc}")

    return VisualFingerprintResponse(
        media_kind=fp.kind,
        representative_frames=fp.representative_count,
        ahashes=[f.ahash for f in fp.frames],
        dhashes=[f.dhash for f in fp.frames],
        notes=[
            "Images produce one visual fingerprint; videos produce several representative-frame fingerprints.",
            "Representative video frames reject blank and near-duplicate frames so intros and repeated frames do not dominate.",
            "Perceptual hashes are intended for similarity matching, not cryptographic identity.",
        ],
    )


@app.post("/v1/compare-visual", response_model=VisualCompareResponse, dependencies=[Depends(require_api_key)])
async def compare_visual_files(
    source: UploadFile = File(..., description="Source screenshot, image, or video"),
    candidate: UploadFile = File(..., description="Candidate image or video"),
):
    _validate_upload(source)
    _validate_upload(candidate)
    ss = Path(source.filename or "source.bin").suffix or ".bin"
    cs = Path(candidate.filename or "candidate.bin").suffix or ".bin"
    with tempfile.TemporaryDirectory(prefix="findrest-visual-compare-") as td:
        sp = Path(td) / f"source{ss}"
        cp = Path(td) / f"candidate{cs}"
        await _save_upload(source, sp)
        await _save_upload(candidate, cp)
        try:
            a = fingerprint_media(str(sp))
            b = fingerprint_media(str(cp))
            score, pairs = visual_similarity(a, b)
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=f"Could not decode supplied visual media: {exc}")

    return VisualCompareResponse(
        visual_similarity=round(score, 4),
        source_kind=a.kind,
        candidate_kind=b.kind,
        source_representative_frames=a.representative_count,
        candidate_representative_frames=b.representative_count,
        frame_pairs_compared=pairs,
        likely_same_visual_source=score >= 0.72,
        notes=[
            "Similarity combines perceptual luminance hashes, edge structure, and color distribution.",
            "The comparison is designed to tolerate resizing, compression, and modest overlays better than exact-pixel matching.",
            "A visual match is evidence of shared imagery; it does not by itself prove authorship or identity.",
        ],
    )


@app.post("/v1/extract-visible-text", response_model=VisibleTextResponse, dependencies=[Depends(require_api_key)])
async def extract_visible_text_file(
    media: UploadFile = File(..., description="User-provided/permitted screenshot, image, or video"),
):
    _validate_upload(media)
    suffix = Path(media.filename or "visible-text.bin").suffix or ".bin"
    with tempfile.TemporaryDirectory(prefix="findrest-visible-text-") as td:
        path = Path(td) / f"source{suffix}"
        await _save_upload(media, path)
        if not path.exists() or path.stat().st_size == 0:
            raise HTTPException(status_code=422, detail="Media was empty")
        try:
            ev = extract_visible_text(str(path))
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=f"Could not inspect supplied media: {exc}")

    return VisibleTextResponse(
        text=ev.text,
        handles=list(ev.handles),
        hashtags=list(ev.hashtags),
        urls=list(ev.urls),
        keywords=list(ev.keywords),
        suggested_queries=visible_text_queries(ev),
        frames_examined=ev.frames_examined,
        backend=ev.backend,
        notes=[
            "Visible text can reveal usernames, watermarks, subtitles, headlines, signs, product names, and other source clues.",
            "For videos, OCR samples multiple frames rather than trusting a single frame.",
            "OCR output is evidence, not ground truth; low-quality or stylized text may be misread.",
        ],
    )



@app.post("/v1/extract-visual-clues", response_model=VisualCluesResponse, dependencies=[Depends(require_api_key)])
async def extract_semantic_visual_clues(
    media: UploadFile = File(..., description="User-provided screenshot, image, or video"),
):
    _validate_upload(media)
    suffix = Path(media.filename or "shared-media.bin").suffix or ".bin"
    with tempfile.TemporaryDirectory(prefix="findrest-visual-clues-") as td:
        path = Path(td) / f"source{suffix}"
        await _save_upload(media, path)
        if not path.exists() or path.stat().st_size == 0:
            raise HTTPException(status_code=422, detail="Shared media was empty")
        try:
            clues = await extract_visual_clues(str(path))
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=f"Could not inspect supplied media: {exc}")

    return VisualCluesResponse(
        objects=list(clues.objects),
        logos=list(clues.logos),
        scenes=list(clues.scenes),
        clothing=list(clues.clothing),
        local_scene_tags=list(clues.local_scene_tags),
        frames_examined=clues.frames_examined,
        provider_status=clues.provider_status,
        suggested_queries=clue_queries(clues),
        notes=[
            "Local scene tags are coarse pixel-derived descriptors, not object-identification claims.",
            "Semantic object, logo, scene, and clothing labels require the optional configured visual-clue provider.",
            "User media is request-scoped and discarded after extraction.",
        ],
    )


@app.post("/v1/discover-media", response_model=MediaDiscoveryResponse, dependencies=[Depends(require_api_key)])
async def discover_shared_media(
    media: UploadFile = File(..., description="Standalone user-provided screenshot, image, or video"),
):
    _validate_upload(media)
    suffix = Path(media.filename or "shared-media.bin").suffix or ".bin"
    with tempfile.TemporaryDirectory(prefix="findrest-discover-media-") as td:
        path = Path(td) / f"source{suffix}"
        await _save_upload(media, path)
        if not path.exists() or path.stat().st_size == 0:
            raise HTTPException(status_code=422, detail="Shared media was empty")
        try:
            visual = fingerprint_media(str(path))
            visible = extract_visible_text(str(path))
            semantic_visual = await extract_visual_clues(str(path))
            candidates, discovery_notes = await discover_from_media(str(path), visible, semantic_visual)
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=f"Could not inspect supplied media: {exc}")

    best = candidates[0] if candidates and candidates[0].score >= 0.36 else None
    confidence = best.score if best else 0.0
    notes = [
        "Standalone media discovery can work without a source URL when visible text provides searchable clues.",
        "Visual fingerprints are created immediately, but this build does not send perceptual hashes to an external reverse-image provider.",
        "A result found through OCR is a likely source/copy candidate, not proof of exact visual identity until visual media is directly compared.",
    ]
    notes.extend(discovery_notes)
    if not visible.text:
        notes.append("No readable text was found. Visual fingerprinting still succeeded, but standalone web discovery needs a future reverse-image provider for text-free images.")

    response = MediaDiscoveryResponse(
        search_id=secrets.token_hex(8),
        media_kind=visual.kind,
        confidence=round(confidence, 4),
        best_match=best,
        candidates=candidates,
        visible_text=visible.text,
        handles=list(visible.handles),
        keywords=list(visible.keywords),
        visual_objects=list(semantic_visual.objects),
        visual_logos=list(semantic_visual.logos),
        visual_scenes=list(semantic_visual.scenes) + list(semantic_visual.local_scene_tags),
        visual_clothing=list(semantic_visual.clothing),
        representative_frames=visual.representative_count,
        notes=notes,
    )
    evidence_paths = ["visual_fingerprint"]
    if visible.text:
        evidence_paths.append("ocr")
    if any(c.evidence.get("reverse_image_match", 0) > 0 for c in candidates):
        evidence_paths.append("reverse_image")
    if any(c.evidence.get("visible_text_match", 0) > 0 for c in candidates):
        evidence_paths.append("visible_text_search")
    if any(c.evidence.get("visual_clue_match", 0) > 0 for c in candidates):
        evidence_paths.append("visual_clue_search")
    record_event(
        "media_discovery",
        success=True,
        found=best is not None,
        media_kind=visual.kind,
        confidence=round(confidence, 4),
        candidate_count=len(candidates),
        representative_frames=visual.representative_count,
        evidence_paths=evidence_paths,
    )
    return response


@app.post("/v1/feedback", response_model=FeedbackResponse, dependencies=[Depends(require_api_key)])
async def submit_feedback(req: FeedbackRequest):
    payload = req.model_dump(mode="json")
    record_feedback(payload)
    record_feedback_case(payload)
    record_event(
        "feedback",
        success=True,
        verdict=req.verdict,
        source_platform=req.source_platform or "unknown",
        search_intent=req.search_intent,
        result_state=req.result_state or "unknown",
        confidence_grade=req.confidence_grade,
        confidence_bucket=(
            "80-100" if (req.confidence or 0) >= .8 else
            "60-79" if (req.confidence or 0) >= .6 else
            "40-59" if (req.confidence or 0) >= .4 else
            "20-39" if (req.confidence or 0) >= .2 else "0-19"
        ),
    )
    return FeedbackResponse(
        accepted=True,
        notes=[
            "Feedback stores coarse quality labels plus hashed identifiers for regression analysis.",
            "Raw best-match URLs are no longer stored; only a short SHA-256 fingerprint is retained.",
            "Raw screenshots, video, transcripts, OCR text, titles, creators, queries, and snippets are not stored.",
        ],
    )


@app.get("/v1/feedback-summary", response_model=FeedbackSummaryResponse, dependencies=[Depends(require_api_key)])
async def feedback_summary():
    data = feedback_case_summary()
    return FeedbackSummaryResponse(
        **data,
        notes=[
            "This summary groups beta feedback into privacy-safe failure patterns.",
            "High-confidence wrong answers are surfaced explicitly because they are the highest-priority calibration regressions.",
            "No raw URLs, media, transcripts, OCR, titles, creators, queries, or filenames are exposed.",
        ],
    )


def _watch_response(watch: dict, *, found: bool = False, message: str = "") -> WatchStatusResponse:
    return WatchStatusResponse(
        watch_id=watch["watch_id"],
        source_url=watch["source_url"],
        scope=watch.get("scope", "web"),
        intent=watch.get("intent", "continue_story"),
        created_at=watch["created_at"],
        last_checked_at=watch.get("last_checked_at"),
        last_result_state=watch.get("last_result_state"),
        last_best_match_url=watch.get("last_best_match_url"),
        active=bool(watch.get("active", True)),
        found=found,
        message=message,
    )



@app.post("/v1/push/register", response_model=PushRegisterResponse, dependencies=[Depends(require_api_key)])
async def register_push_device(req: PushRegisterRequest):
    record = register_device(req.installation_id, req.device_token, req.environment)
    return PushRegisterResponse(
        registered=True,
        installation_id=req.installation_id,
        token_fingerprint=record["token_fingerprint"],
        push_configured=bool(os.getenv("FINDREST_PUSH_ENDPOINT", "").strip()),
        notes=[
            "The backend stores the APNs device token only for notification delivery.",
            "The API response exposes only a short token fingerprint, never the raw device token.",
            "Actual delivery requires FINDREST_PUSH_ENDPOINT to point to a trusted APNs gateway.",
        ],
    )

@app.delete("/v1/push/{installation_id}", response_model=PushUnregisterResponse, dependencies=[Depends(require_api_key)])
async def remove_push_device(installation_id: str):
    return PushUnregisterResponse(
        removed=unregister_device(installation_id),
        installation_id=installation_id,
    )


@app.post("/v1/watch", response_model=WatchStatusResponse, dependencies=[Depends(require_api_key)])
async def create_continuation_watch(req: WatchCreateRequest):
    watch = create_watch(str(req.source_url), req.scope, req.installation_id, req.intent)
    return _watch_response(
        watch,
        found=False,
        message="Watch saved. This build supports later re-checks without retaining the original media.",
    )

@app.get("/v1/watch/{watch_id}", response_model=WatchStatusResponse, dependencies=[Depends(require_api_key)])
async def get_continuation_watch(watch_id: str):
    watch = get_watch(watch_id)
    if not watch:
        raise HTTPException(status_code=404, detail="Watch not found")
    found = is_success_state(watch.get("last_result_state"))
    return _watch_response(watch, found=found, message="Watch status loaded.")

@app.post("/v1/watch/{watch_id}/check", response_model=WatchCheckResponse, dependencies=[Depends(require_api_key)])
async def check_continuation_watch(watch_id: str):
    watch = get_watch(watch_id)
    if not watch:
        raise HTTPException(status_code=404, detail="Watch not found")
    req = AnalyzeRequest(
        url=watch["source_url"],
        scope=watch.get("scope", "web"),
        intent=watch.get("intent", "continue_story"),
    )
    result = await analyze(req)
    found = is_success_state(result.result_state)
    updated = update_watch(
        watch_id,
        last_checked_at=datetime.now(timezone.utc).isoformat(),
        last_result_state=result.result_state,
        last_best_match_url=str(result.best_match.url) if result.best_match else None,
        active=not found,
    )
    if found:
        await send_found_notification(
            installation_id=watch.get("installation_id"),
            watch_id=watch_id,
            result_state=result.result_state,
            best_match_url=str(result.best_match.url) if result.best_match else None,
        )
    return WatchCheckResponse(
        watch=_watch_response(
            updated,
            found=found,
            message="A credible result was found." if found else "No credible result for this saved goal was found on this check.",
        ),
        result=result,
    )






@app.get("/v1/benchmark", response_model=BenchmarkSummaryResponse, dependencies=[Depends(require_api_key)])
async def benchmark():
    data = benchmark_summary()
    return BenchmarkSummaryResponse(
        **data,
        notes=[
            "This deterministic benchmark exercises adversarial ranking and outcome behaviors without external network access.",
            "It includes false Part 2 labels, same-creator unrelated material, reposts, full originals, duplicate parts, tracking variants, no-answer cases, and ordering traps.",
            "Visual crop/mirror, audio-reencoding, OCR, and multimodal media robustness remain covered by the dedicated automated media tests.",
        ],
    )



@app.get("/v1/beta-readiness", response_model=BetaReadinessResponse, dependencies=[Depends(require_api_key)])
async def beta_readiness():
    data = readiness_summary()
    return BetaReadinessResponse(
        **data,
        notes=[
            "Beta readiness is intentionally conservative: every critical gate must pass.",
            "Optional provider gates can remain false during development, but missing providers reduce real-world coverage.",
            "This endpoint checks deterministic benchmark and deployment configuration; it does not replace TestFlight/device testing.",
        ],
    )


@app.get("/v1/diagnostics", response_model=DiagnosticsSummaryResponse, dependencies=[Depends(require_api_key)])
async def diagnostics():
    data = diagnostics_summary()
    return DiagnosticsSummaryResponse(
        **data,
        notes=[
            "Diagnostics contain coarse operational metrics only.",
            "Raw URLs, screenshots, videos, transcripts, OCR text, creators, search queries, device tokens, and filenames are not stored.",
            "Metrics are intended for beta quality monitoring and confidence calibration, not user profiling.",
        ],
    )


@app.get("/v1/capabilities", response_model=CapabilitiesResponse, dependencies=[Depends(require_api_key)])
async def capabilities():
    return CapabilitiesResponse(
        youtube_search=bool(os.getenv("YOUTUBE_API_KEY", "").strip()),
        open_web_search=bool(os.getenv("BRAVE_SEARCH_API_KEY", "").strip()),
        reverse_image_search=bool(os.getenv("FINDREST_REVERSE_IMAGE_ENDPOINT", "").strip()),
        local_transcription=os.getenv("ENABLE_LOCAL_TRANSCRIPTION", "0").strip().lower() in {"1","true","yes"} or os.getenv("FINDREST_LOCAL_WHISPER", "0").strip().lower() in {"1","true","yes"},
        watch_store=True,
        feedback_store=True,
        push_notifications=bool(os.getenv("FINDREST_PUSH_ENDPOINT", "").strip()),
        watch_storage_backend=storage_info()["backend"],
        candidate_media_verification=candidate_media_configured(),
        notes=[
            "Disabled capabilities indicate missing configuration, not an app failure.",
            "Private/restricted social content is never bypassed.",
        ],
    )

@app.get("/v1/watches", response_model=WatchListResponse, dependencies=[Depends(require_api_key)])
async def active_watches():
    watches = [
        _watch_response(
            w,
            found=is_success_state(w.get("last_result_state")),
            message="Active continuation watch.",
        )
        for w in list_active()
    ]
    return WatchListResponse(watches=watches)




@app.post("/v1/watches/check-due", response_model=WatchBatchCheckResponse, dependencies=[Depends(require_api_key)])
async def check_due_watches():
    """Bounded continuation-watch batch runner.

    A deployment scheduler may call it periodically using the normal server API key.
    When a credible result is found, configured push delivery is attempted.
    """
    try:
        interval = int(os.getenv("FINDREST_WATCH_INTERVAL_MINUTES", "360"))
    except ValueError:
        interval = 360
    try:
        limit = int(os.getenv("FINDREST_WATCH_BATCH_SIZE", "10"))
    except ValueError:
        limit = 10
    interval = max(60, min(interval, 10080))
    limit = max(1, min(limit, 25))

    due = list_due(interval_minutes=interval, limit=limit)
    items: list[WatchBatchCheckItem] = []
    found_count = 0

    for watch in due:
        watch_id = watch["watch_id"]
        try:
            req = AnalyzeRequest(
        url=watch["source_url"],
        scope=watch.get("scope", "web"),
        intent=watch.get("intent", "continue_story"),
    )
            result = await analyze(req)
            found = is_success_state(result.result_state)
            if found:
                found_count += 1
            update_watch(
                watch_id,
                last_checked_at=datetime.now(timezone.utc).isoformat(),
                last_result_state=result.result_state,
                last_best_match_url=str(result.best_match.url) if result.best_match else None,
                active=not found,
            )
            push_sent = False
            push_status = None
            if found:
                push_sent, push_status = await send_found_notification(
                    installation_id=watch.get("installation_id"),
                    watch_id=watch_id,
                    result_state=result.result_state,
                    best_match_url=str(result.best_match.url) if result.best_match else None,
                )
            items.append(WatchBatchCheckItem(
                watch_id=watch_id,
                checked=True,
                found=found,
                result_state=result.result_state,
                best_match_url=result.best_match.url if result.best_match else None,
                push_sent=push_sent,
                push_status=push_status,
            ))
        except Exception as exc:
            # One bad source must not abort the entire scheduler batch.
            items.append(WatchBatchCheckItem(
                watch_id=watch_id,
                checked=False,
                found=False,
                error=exc.__class__.__name__,
            ))

    return WatchBatchCheckResponse(
        checked=sum(1 for x in items if x.checked),
        found=found_count,
        remaining_active=len(list_active()),
        items=items,
        notes=[
            f"Checked at most {limit} watches that were due after {interval} minutes.",
            "This execution hook can be invoked by the included authenticated deployment scheduler.",
            "When push delivery is configured, credible found results trigger a notification attempt.",
            "A failed watch is isolated so other due watches can still be checked.",
        ],
    )


@app.delete("/v1/watch/{watch_id}", response_model=WatchDeleteResponse, dependencies=[Depends(require_api_key)])
async def remove_continuation_watch(watch_id: str):
    watch = deactivate_watch(watch_id)
    if not watch:
        raise HTTPException(status_code=404, detail="Watch not found")
    return WatchDeleteResponse(
        removed=True,
        watch_id=watch_id,
        message="Watch removed. The source will no longer appear in the active watch list.",
    )



@app.post("/v1/compare-appearance", response_model=AppearanceCompareResponse, dependencies=[Depends(require_api_key)])
async def compare_appearance_files(
    source: UploadFile = File(..., description="Source user-provided/permitted image or video"),
    candidate: UploadFile = File(..., description="Candidate user-provided/permitted image or video"),
):
    """Pairwise appearance comparison for a specific search.

    This is not an identity service. It does not assign names, search a person
    database, or retain reusable biometric templates.
    """
    _validate_upload(source)
    _validate_upload(candidate)
    ss = Path(source.filename or "source.mp4").suffix or ".mp4"
    cs = Path(candidate.filename or "candidate.mp4").suffix or ".mp4"
    with tempfile.TemporaryDirectory(prefix="findrest-appearance-") as td:
        sp = Path(td) / f"source{ss}"
        cp = Path(td) / f"candidate{cs}"
        await _save_upload(source, sp)
        await _save_upload(candidate, cp)
        if not sp.exists() or not cp.exists() or sp.stat().st_size == 0 or cp.stat().st_size == 0:
            raise HTTPException(status_code=422, detail="Source and candidate media must both be non-empty")
        try:
            result = compare_appearance(str(sp), str(cp))
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=f"Could not decode supplied media: {exc}")

    record_event(
        "appearance_comparison",
        success=True,
        frames_compared=result.frames_compared,
        likely_same_visible_person=result.likely_same_visible_person,
        appearance_similarity=result.combined_similarity,
        evidence_paths=["face_region", "clothing_region", "scene_region"],
    )
    return AppearanceCompareResponse(
        face_region_similarity=result.face_region_similarity,
        clothing_region_similarity=result.clothing_region_similarity,
        scene_region_similarity=result.scene_region_similarity,
        combined_similarity=result.combined_similarity,
        frames_compared=result.frames_compared,
        likely_same_visible_person=result.likely_same_visible_person,
        notes=[
            "This compares broad visual appearance regions only within the submitted media pair.",
            "The face-region score is a local visual-region similarity signal, not identity recognition.",
            "No name, identity, face database, or reusable biometric profile is created.",
            "Uploaded media remains request-scoped and is discarded after comparison.",
        ],
    )


@app.post("/v1/compare-visual-robust", response_model=RobustVisualCompareResponse, dependencies=[Depends(require_api_key)])
async def compare_visual_robust_files(
    source: UploadFile = File(..., description="Source screenshot, image, or permitted video"),
    candidate: UploadFile = File(..., description="Candidate image or permitted video"),
):
    _validate_upload(source)
    _validate_upload(candidate)
    ss = Path(source.filename or "source.bin").suffix or ".bin"
    cs = Path(candidate.filename or "candidate.bin").suffix or ".bin"
    with tempfile.TemporaryDirectory(prefix="findrest-robust-visual-") as td:
        sp = Path(td) / f"source{ss}"
        cp = Path(td) / f"candidate{cs}"
        await _save_upload(source, sp)
        await _save_upload(candidate, cp)
        try:
            score, pairs = robust_media_similarity(str(sp), str(cp))
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=f"Could not decode supplied visual media: {exc}")
    return RobustVisualCompareResponse(
        robust_visual_similarity=round(score, 4),
        frame_pairs_compared=pairs,
        likely_same_visual_source=score >= 0.76,
        transformations_checked=["center crop", "top-caption crop", "bottom-caption crop", "horizontal mirror"],
        notes=[
            "Robust comparison is designed for reposts altered by cropping, mirroring, aspect changes, or caption overlays.",
            "It compares only user-provided/permitted media and does not identify people.",
            "A visual match is evidence of shared imagery, not proof of authorship or chronology.",
        ],
    )


@app.post("/v1/compare-audio-fingerprint", response_model=AudioFingerprintCompareResponse, dependencies=[Depends(require_api_key)])
async def compare_audio_fingerprint_files(
    source: UploadFile = File(..., description="Source user-provided/permitted audio or video"),
    candidate: UploadFile = File(..., description="Candidate user-provided/permitted audio or video"),
):
    _validate_upload(source)
    _validate_upload(candidate)
    ss = Path(source.filename or "source.mp4").suffix or ".mp4"
    cs = Path(candidate.filename or "candidate.mp4").suffix or ".mp4"
    with tempfile.TemporaryDirectory(prefix="findrest-audio-fingerprint-") as td:
        sp = Path(td) / f"source{ss}"
        cp = Path(td) / f"candidate{cs}"
        await _save_upload(source, sp)
        await _save_upload(candidate, cp)
        try:
            source_fp = fingerprint_audio(str(sp))
            candidate_fp = fingerprint_audio(str(cp))
            score, pairs = audio_fingerprint_similarity(source_fp, candidate_fp)
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=f"Could not decode supplied audio media: {exc}")
    return AudioFingerprintCompareResponse(
        audio_fingerprint_similarity=round(score, 4),
        source_windows=source_fp.windows,
        candidate_windows=candidate_fp.windows,
        likely_same_audio=score >= .72 and min(source_fp.windows, candidate_fp.windows) >= 2,
        notes=[
            "Spectral fingerprints compare audio across the whole permitted clips rather than only at the boundary.",
            "The representation is normalized for volume and designed to tolerate ordinary social-media re-encoding.",
            "A match indicates shared audio characteristics; it does not identify a speaker or prove authorship.",
        ],
    )



def _verification_response_from_paths(
    source_path: str,
    candidate_path: str,
    *,
    source_transcript: str | None = None,
    candidate_transcript: str | None = None,
) -> MultimodalVerifyResponse:
    robust_visual, _ = robust_media_similarity(source_path, candidate_path)
    boundary = compare_media(source_path, candidate_path)
    semantic = compare_semantics(
        source_path,
        candidate_path,
        source_transcript=source_transcript,
        candidate_transcript=candidate_transcript,
    )
    source_audio_fp = fingerprint_audio(source_path)
    candidate_audio_fp = fingerprint_audio(candidate_path)
    audio_fp, _ = audio_fingerprint_similarity(source_audio_fp, candidate_audio_fp)
    appearance = compare_appearance(source_path, candidate_path)

    has_audio_fp = min(source_audio_fp.windows, candidate_audio_fp.windows) >= 2
    has_appearance = appearance.frames_compared > 0
    has_boundary_audio = boundary.audio_samples >= 256
    has_transcript = bool(semantic.source_transcript and semantic.candidate_transcript)

    fused = fuse_verification(VerificationSignals(
        robust_visual=robust_visual,
        audio_fingerprint=audio_fp,
        boundary_visual=boundary.visual,
        boundary_audio=boundary.audio,
        transcript_semantic=semantic.transcript,
        scene_semantic=semantic.scene,
        appearance_similarity=appearance.combined_similarity,
        has_appearance=has_appearance,
        has_audio_fingerprint=has_audio_fp,
        has_boundary_audio=has_boundary_audio,
        has_transcript=has_transcript,
    ))

    response = MultimodalVerifyResponse(
        verdict=fused.verdict,
        confidence=round(fused.confidence, 4),
        agreement_count=fused.agreement_count,
        contradiction_penalty=round(fused.contradiction_penalty, 4),
        robust_visual_similarity=round(robust_visual, 4),
        audio_fingerprint_similarity=round(audio_fp if has_audio_fp else 0.0, 4),
        boundary_visual_continuity=round(boundary.visual, 4),
        boundary_audio_continuity=round(boundary.audio if has_boundary_audio else 0.0, 4),
        transcript_semantic=round(semantic.transcript if has_transcript else 0.0, 4),
        scene_semantic=round(semantic.scene, 4),
        appearance_similarity=appearance.combined_similarity,
        face_region_similarity=appearance.face_region_similarity,
        clothing_region_similarity=appearance.clothing_region_similarity,
        contributions=fused.contributions,
        transcript_backend=semantic.transcript_backend,
        notes=[
            "This endpoint fuses independent visual, audio, semantic, and boundary evidence in one verification pass.",
            "Unavailable channels are omitted from the weighted denominator rather than treated as negative evidence.",
            "Agreement across independent channels raises confidence modestly; strong contradictions suppress overconfidence.",
            "Appearance evidence compares broad face/upper-body, clothing, and scene regions only; it does not identify or name a person.",
            "No reusable biometric profile or face database is created or retained.",
            "Only user-provided/permitted media is compared. No restricted social media is downloaded.",
        ],
    )
    paths = ["robust_visual", "boundary_visual", "scene_semantic"]
    if has_appearance:
        paths.append("appearance_similarity")
    if has_audio_fp:
        paths.append("audio_fingerprint")
    if has_boundary_audio:
        paths.append("boundary_audio")
    if has_transcript:
        paths.append("transcript_semantic")
    record_event(
        "media_verification",
        success=True,
        verdict=fused.verdict,
        confidence=round(fused.confidence, 4),
        agreement_count=fused.agreement_count,
        contradiction_penalty=round(fused.contradiction_penalty, 4),
        evidence_paths=paths,
    )
    return response




@app.post("/v1/verify-candidate-url", response_model=CandidateURLVerifyResponse, dependencies=[Depends(require_api_key)])
async def verify_candidate_url(
    candidate_url: str = Form(...),
    source: UploadFile = File(..., description="User-provided/permitted source video"),
    source_transcript: str | None = Form(default=None),
):
    """Automatically verify a discovered candidate through a permitted-media gateway.

    The backend never downloads candidate_url directly. It sends the URL to the
    configured gateway, which may return media only when the deployment is licensed
    or otherwise permitted to process it.
    """
    _validate_upload(source)
    if not candidate_media_configured():
        return CandidateURLVerifyResponse(
            candidate_url=candidate_url,
            provider_status="provider_not_configured",
            verified=False,
            verification=None,
            notes=["Automatic candidate verification requires a configured permitted-media gateway."],
        )

    ss = Path(source.filename or "source.mp4").suffix or ".mp4"
    with tempfile.TemporaryDirectory(prefix="findrest-auto-verify-") as td:
        sp = Path(td) / f"source{ss}"
        await _save_upload(source, sp)
        if not sp.exists() or sp.stat().st_size == 0:
            raise HTTPException(status_code=422, detail="Source media was empty")

        fetched = await fetch_permitted_candidate_media(candidate_url, td)
        if not fetched.path:
            record_event(
                "candidate_url_verification",
                success=False,
                provider_status=fetched.status,
                evidence_paths=["permitted_media_gateway"],
            )
            return CandidateURLVerifyResponse(
                candidate_url=candidate_url,
                provider_status=fetched.status,
                verified=False,
                verification=None,
                notes=[
                    "The configured gateway did not return permitted candidate media.",
                    "Find the Rest did not directly download the candidate URL.",
                ],
            )

        try:
            verification = _verification_response_from_paths(
                str(sp),
                fetched.path,
                source_transcript=source_transcript,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=f"Could not decode permitted candidate media: {exc}")

    verified = verification.verdict in {"strong_match", "likely_match"}
    record_event(
        "candidate_url_verification",
        success=True,
        provider_status="ok",
        verified=verified,
        verdict=verification.verdict,
        confidence=verification.confidence,
        evidence_paths=["permitted_media_gateway", "multimodal_verification"],
    )
    return CandidateURLVerifyResponse(
        candidate_url=candidate_url,
        provider_status="ok",
        verified=verified,
        verification=verification,
        notes=[
            "Candidate media came only from the configured permitted-media gateway.",
            "The candidate URL itself was not downloaded directly by Find the Rest.",
        ],
    )



@app.post("/v1/verify-ranked-candidates", response_model=VerificationRerankResponse, dependencies=[Depends(require_api_key)])
async def verify_ranked_candidates(
    candidates_json: str = Form(..., description="JSON array of ranked Candidate objects"),
    source: UploadFile = File(..., description="User-provided/permitted source video"),
    source_transcript: str | None = Form(default=None),
):
    """Verify and rerank the top discovered candidates using permitted media only.

    Provider cost is intentionally bounded. By default only the top two candidates
    are attempted, with an absolute maximum of three.
    """
    _validate_upload(source)
    if not candidate_media_configured():
        return VerificationRerankResponse(
            ranked=[],
            verified_count=0,
            provider_attempts=0,
            changed_top_candidate=False,
            notes=["Automatic verification reranking requires a configured permitted-media gateway."],
        )

    try:
        raw = json.loads(candidates_json)
        if not isinstance(raw, list):
            raise ValueError
        parsed = [Candidate.model_validate(item) for item in raw[:3]]
    except Exception:
        raise HTTPException(status_code=422, detail="candidates_json must be a valid JSON array of Candidate objects")

    if not parsed:
        raise HTTPException(status_code=422, detail="At least one candidate is required")

    try:
        max_attempts = int(os.getenv("FINDREST_VERIFICATION_RERANK_MAX_CANDIDATES", "2"))
    except ValueError:
        max_attempts = 2
    max_attempts = max(1, min(max_attempts, 3))
    parsed = parsed[:max_attempts]

    ss = Path(source.filename or "source.mp4").suffix or ".mp4"
    verification_items = []
    provider_statuses: list[str] = []
    response_verifications = []

    with tempfile.TemporaryDirectory(prefix="findrest-rerank-") as td:
        sp = Path(td) / f"source{ss}"
        await _save_upload(source, sp)
        if not sp.exists() or sp.stat().st_size == 0:
            raise HTTPException(status_code=422, detail="Source media was empty")

        for idx, candidate in enumerate(parsed):
            candidate_dir = Path(td) / f"candidate-{idx}"
            candidate_dir.mkdir(parents=True, exist_ok=True)
            fetched = await fetch_permitted_candidate_media(str(candidate.url), str(candidate_dir))
            verification = None
            if fetched.path:
                try:
                    verification = _verification_response_from_paths(
                        str(sp),
                        fetched.path,
                        source_transcript=source_transcript,
                    )
                except RuntimeError:
                    fetched = fetched.__class__(
                        path=None,
                        status="candidate_decode_failed",
                        content_type=fetched.content_type,
                        bytes_written=fetched.bytes_written,
                    )
            verification_items.append((candidate, verification, fetched.status))
            provider_statuses.append(fetched.status)
            response_verifications.append(verification)

    reranked = rerank_verified_candidates(verification_items)
    by_url = {
        str(candidate.url): (status, verification)
        for (candidate, verification, status) in verification_items
    }
    original_top = str(parsed[0].url)
    new_top = str(reranked[0].candidate.url) if reranked else None

    ranked_models = []
    for item in reranked:
        status, verification = by_url[str(item.candidate.url)]
        ranked_models.append(VerificationRankedCandidateResponse(
            candidate=item.candidate,
            original_score=item.candidate.score,
            adjusted_score=item.adjusted_score,
            delta=item.delta,
            disposition=item.disposition,
            provider_status=status,
            verification=verification,
        ))

    verified_count = sum(
        1 for verification in response_verifications
        if verification is not None and verification.verdict in {"strong_match", "likely_match"}
    )
    record_event(
        "verification_rerank",
        success=True,
        provider_attempts=len(parsed),
        verified_count=verified_count,
        changed_top_candidate=bool(new_top and new_top != original_top),
        evidence_paths=["permitted_media_gateway", "multimodal_verification", "verification_rerank"],
    )
    return VerificationRerankResponse(
        ranked=ranked_models,
        verified_count=verified_count,
        provider_attempts=len(parsed),
        changed_top_candidate=bool(new_top and new_top != original_top),
        top_candidate_url=new_top,
        notes=[
            "Media verification is a bounded reranking signal; it does not overwrite story or provenance evidence.",
            "Strong/likely media matches can promote a candidate modestly; failed verification demotes but does not erase it.",
            f"At most {max_attempts} candidate(s) were attempted to control provider cost and latency.",
        ],
    )


@app.post("/v1/verify-media-pair", response_model=MultimodalVerifyResponse, dependencies=[Depends(require_api_key)])
async def verify_media_pair(
    source: UploadFile = File(..., description="Source user-provided/permitted video"),
    candidate: UploadFile = File(..., description="Candidate user-provided/permitted video"),
    source_transcript: str | None = Form(default=None),
    candidate_transcript: str | None = Form(default=None),
):
    _validate_upload(source)
    _validate_upload(candidate)
    ss = Path(source.filename or "source.mp4").suffix or ".mp4"
    cs = Path(candidate.filename or "candidate.mp4").suffix or ".mp4"

    with tempfile.TemporaryDirectory(prefix="findrest-multimodal-") as td:
        sp = Path(td) / f"source{ss}"
        cp = Path(td) / f"candidate{cs}"
        await _save_upload(source, sp)
        await _save_upload(candidate, cp)
        if not sp.exists() or not cp.exists() or sp.stat().st_size == 0 or cp.stat().st_size == 0:
            raise HTTPException(status_code=422, detail="Source and candidate media must both be non-empty")
        try:
            return _verification_response_from_paths(
                str(sp),
                str(cp),
                source_transcript=source_transcript,
                candidate_transcript=candidate_transcript,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=f"Could not decode supplied media: {exc}")
