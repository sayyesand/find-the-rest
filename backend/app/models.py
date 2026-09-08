from typing import Literal
from pydantic import BaseModel, HttpUrl, Field

Platform = Literal["youtube", "instagram", "facebook", "tiktok", "x", "reddit", "web", "unknown"]
SearchIntent = Literal["continue_story", "full_original", "original_source", "other_copies", "identify_shown"]
MatchType = Literal["official_continuation", "continuation_repost", "full_original", "no_match"]

class AnalyzeRequest(BaseModel):
    url: HttpUrl
    scope: Literal["creator", "social", "web"] = "web"
    intent: SearchIntent = "continue_story"

class LocalClueAnalyzeRequest(BaseModel):
    url: HttpUrl
    scope: Literal["creator", "social", "web"] = "web"
    intent: SearchIntent = "continue_story"
    transcript: str | None = Field(default=None, max_length=20000)
    visible_text: str | None = Field(default=None, max_length=12000)

class Candidate(BaseModel):
    title: str
    url: HttpUrl
    platform: Platform
    creator: str | None = None
    published_at: str | None = None
    thumbnail_url: HttpUrl | None = None
    reason: str
    snippet: str | None = None
    score: float = Field(ge=0, le=1)
    evidence: dict[str, float] = Field(default_factory=dict)
    matched_details: dict[str, list[str]] = Field(default_factory=dict)
    duration_seconds: float | None = Field(default=None, ge=0)
    trace_role: str | None = None
    trace_score: float = Field(default=0.0, ge=0, le=1)

class ChainNode(BaseModel):
    candidate: Candidate
    inferred_part: int | None = Field(default=None, ge=1)
    episode_number: int | None = Field(default=None, ge=1)
    relationship: Literal["continuation", "update", "full_original", "related"]
    chain_score: float = Field(ge=0, le=1)
    order_reason: str

class SearchCoverageModel(BaseModel):
    provider_configured: bool = False
    attempted: int = Field(default=0, ge=0)
    completed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    coverage_ratio: float = Field(default=0.0, ge=0, le=1)
    broad_enough_for_nonpublication_hint: bool = False

class AnalyzeResponse(BaseModel):
    search_id: str | None = None
    search_intent: SearchIntent = "continue_story"
    source_platform: Platform
    source_url: HttpUrl
    match_type: MatchType
    confidence: float = Field(ge=0, le=1)
    confidence_grade: Literal["high", "moderate", "tentative", "low"] = "low"
    evidence_family_count: int = Field(default=0, ge=0)
    strong_evidence_family_count: int = Field(default=0, ge=0)
    best_match: Candidate | None
    candidates: list[Candidate]
    continuation_chain: list[ChainNode] = Field(default_factory=list)
    chain_confidence: float = Field(default=0.0, ge=0, le=1)
    missing_parts: list[int] = Field(default_factory=list)
    recovered_parts: list[int] = Field(default_factory=list)
    result_state: str = "no_verified_match"
    result_message: str = ""
    result_state_confidence: float = Field(default=0.0, ge=0, le=1)
    available_actions: list[str] = Field(default_factory=list)
    provenance_graph: "ProvenanceGraphModel | None" = None
    search_coverage: SearchCoverageModel = Field(default_factory=SearchCoverageModel)
    notes: list[str]

class MediaCompareResponse(BaseModel):
    visual_continuity: float = Field(ge=0, le=1)
    audio_continuity: float = Field(ge=0, le=1)
    combined_media_confidence: float = Field(ge=0, le=1)
    visual_frames_compared: int
    audio_samples_compared: int
    notes: list[str] = Field(default_factory=list)


class SemanticCompareResponse(BaseModel):
    transcript_semantic: float = Field(ge=0, le=1)
    scene_semantic: float = Field(ge=0, le=1)
    combined_semantic_confidence: float = Field(ge=0, le=1)
    transcript_backend: str
    source_transcript: str | None = None
    candidate_transcript: str | None = None
    scene_frames_compared: int
    notes: list[str] = Field(default_factory=list)


class ChainLinkVerification(BaseModel):
    from_index: int = Field(ge=0)
    to_index: int = Field(ge=1)
    from_name: str
    to_name: str
    visual_continuity: float = Field(ge=0, le=1)
    audio_continuity: float = Field(ge=0, le=1)
    transcript_semantic: float = Field(ge=0, le=1)
    scene_semantic: float = Field(ge=0, le=1)
    link_confidence: float = Field(ge=0, le=1)
    verified: bool
    notes: list[str] = Field(default_factory=list)

class ChainVerifyResponse(BaseModel):
    links: list[ChainLinkVerification]
    overall_chain_confidence: float = Field(ge=0, le=1)
    verified_links: int = Field(ge=0)
    total_links: int = Field(ge=0)
    notes: list[str] = Field(default_factory=list)


class VisualFingerprintResponse(BaseModel):
    media_kind: Literal["image", "video"]
    representative_frames: int = Field(ge=1)
    ahashes: list[str]
    dhashes: list[str]
    notes: list[str] = Field(default_factory=list)

class VisualCompareResponse(BaseModel):
    visual_similarity: float = Field(ge=0, le=1)
    source_kind: Literal["image", "video"]
    candidate_kind: Literal["image", "video"]
    source_representative_frames: int = Field(ge=1)
    candidate_representative_frames: int = Field(ge=1)
    frame_pairs_compared: int = Field(ge=1)
    likely_same_visual_source: bool
    notes: list[str] = Field(default_factory=list)


class VisibleTextResponse(BaseModel):
    text: str
    handles: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    suggested_queries: list[str] = Field(default_factory=list)
    frames_examined: int = Field(ge=0)
    backend: str
    notes: list[str] = Field(default_factory=list)



class VisualCluesResponse(BaseModel):
    objects: list[str] = Field(default_factory=list)
    logos: list[str] = Field(default_factory=list)
    scenes: list[str] = Field(default_factory=list)
    clothing: list[str] = Field(default_factory=list)
    local_scene_tags: list[str] = Field(default_factory=list)
    frames_examined: int = Field(default=0, ge=0)
    provider_status: str
    suggested_queries: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

class MediaDiscoveryResponse(BaseModel):
    search_id: str | None = None
    media_kind: Literal["image", "video"]
    confidence: float = Field(ge=0, le=1)
    best_match: Candidate | None = None
    candidates: list[Candidate] = Field(default_factory=list)
    visible_text: str = ""
    handles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    visual_objects: list[str] = Field(default_factory=list)
    visual_logos: list[str] = Field(default_factory=list)
    visual_scenes: list[str] = Field(default_factory=list)
    visual_clothing: list[str] = Field(default_factory=list)
    representative_frames: int = Field(ge=1)
    notes: list[str] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    search_id: str
    verdict: Literal["correct", "wrong", "not_enough_information"]
    best_match_url: HttpUrl | None = None
    source_platform: Platform | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    search_intent: SearchIntent = "continue_story"
    result_state: str | None = Field(default=None, max_length=64)
    confidence_grade: Literal["high", "moderate", "tentative", "low"] = "low"
    evidence_family_count: int = Field(default=0, ge=0, le=20)
    strong_evidence_family_count: int = Field(default=0, ge=0, le=20)

class FeedbackResponse(BaseModel):
    accepted: bool
    notes: list[str] = Field(default_factory=list)



class FeedbackPatternResponse(BaseModel):
    source_platform: str
    search_intent: str
    result_state: str
    confidence_grade: str
    confidence_bucket: str
    count: int = Field(ge=1)

class FeedbackSummaryResponse(BaseModel):
    cases: int = Field(ge=0)
    verdict_counts: dict[str, int] = Field(default_factory=dict)
    failure_cases: int = Field(ge=0)
    high_confidence_wrong: int = Field(ge=0)
    top_failure_patterns: list[FeedbackPatternResponse] = Field(default_factory=list)
    storage: str
    notes: list[str] = Field(default_factory=list)

class WatchCreateRequest(BaseModel):
    source_url: HttpUrl
    scope: Literal["creator", "social", "web"] = "web"
    intent: SearchIntent = "continue_story"
    installation_id: str | None = Field(default=None, min_length=8, max_length=128)

class WatchStatusResponse(BaseModel):
    watch_id: str
    source_url: HttpUrl
    scope: str
    intent: SearchIntent = "continue_story"
    created_at: str
    last_checked_at: str | None = None
    last_result_state: str | None = None
    last_best_match_url: HttpUrl | None = None
    active: bool = True
    found: bool = False
    message: str = ""

class WatchCheckResponse(BaseModel):
    watch: WatchStatusResponse
    result: AnalyzeResponse | None = None


class WatchListResponse(BaseModel):
    watches: list[WatchStatusResponse] = Field(default_factory=list)

class CapabilitiesResponse(BaseModel):
    youtube_search: bool
    open_web_search: bool
    reverse_image_search: bool
    local_transcription: bool
    watch_store: bool
    feedback_store: bool
    push_notifications: bool = False
    watch_storage_backend: str = "unknown"
    candidate_media_verification: bool = False
    notes: list[str] = Field(default_factory=list)


class WatchDeleteResponse(BaseModel):
    removed: bool
    watch_id: str
    message: str


class RobustVisualCompareResponse(BaseModel):
    robust_visual_similarity: float = Field(ge=0, le=1)
    frame_pairs_compared: int = Field(ge=1)
    likely_same_visual_source: bool
    transformations_checked: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ProvenanceNodeModel(BaseModel):
    node_id: str
    label: str
    url: HttpUrl
    role: str
    score: float = Field(ge=0, le=1)
    creator: str | None = None
    published_at: str | None = None

class ProvenanceEdgeModel(BaseModel):
    from_id: str
    to_id: str
    relationship: str
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)

class ProvenanceGraphModel(BaseModel):
    nodes: list[ProvenanceNodeModel] = Field(default_factory=list)
    edges: list[ProvenanceEdgeModel] = Field(default_factory=list)
    likely_origin_node_id: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)


class AudioFingerprintCompareResponse(BaseModel):
    audio_fingerprint_similarity: float = Field(ge=0, le=1)
    source_windows: int = Field(ge=0)
    candidate_windows: int = Field(ge=0)
    likely_same_audio: bool
    notes: list[str] = Field(default_factory=list)



class AppearanceCompareResponse(BaseModel):
    face_region_similarity: float = Field(ge=0, le=1)
    clothing_region_similarity: float = Field(ge=0, le=1)
    scene_region_similarity: float = Field(ge=0, le=1)
    combined_similarity: float = Field(ge=0, le=1)
    frames_compared: int = Field(ge=0)
    likely_same_visible_person: bool
    notes: list[str] = Field(default_factory=list)

class MultimodalVerifyResponse(BaseModel):
    verdict: Literal["strong_match", "likely_match", "possible_match", "not_verified"]
    confidence: float = Field(ge=0, le=1)
    agreement_count: int = Field(ge=0)
    contradiction_penalty: float = Field(ge=0, le=1)
    robust_visual_similarity: float = Field(ge=0, le=1)
    audio_fingerprint_similarity: float = Field(ge=0, le=1)
    boundary_visual_continuity: float = Field(ge=0, le=1)
    boundary_audio_continuity: float = Field(ge=0, le=1)
    transcript_semantic: float = Field(ge=0, le=1)
    scene_semantic: float = Field(ge=0, le=1)
    appearance_similarity: float = Field(default=0.0, ge=0, le=1)
    face_region_similarity: float = Field(default=0.0, ge=0, le=1)
    clothing_region_similarity: float = Field(default=0.0, ge=0, le=1)
    contributions: dict[str, float] = Field(default_factory=dict)
    transcript_backend: str
    notes: list[str] = Field(default_factory=list)


class WatchBatchCheckItem(BaseModel):
    watch_id: str
    checked: bool
    found: bool
    result_state: str | None = None
    best_match_url: HttpUrl | None = None
    push_sent: bool = False
    push_status: str | None = None
    error: str | None = None

class WatchBatchCheckResponse(BaseModel):
    checked: int = Field(ge=0)
    found: int = Field(ge=0)
    remaining_active: int = Field(ge=0)
    items: list[WatchBatchCheckItem] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PushRegisterRequest(BaseModel):
    installation_id: str = Field(min_length=8, max_length=128)
    device_token: str = Field(min_length=32, max_length=512)
    environment: Literal["sandbox", "production"] = "sandbox"

class PushRegisterResponse(BaseModel):
    registered: bool
    installation_id: str
    token_fingerprint: str
    push_configured: bool
    notes: list[str] = Field(default_factory=list)

class PushUnregisterResponse(BaseModel):
    removed: bool
    installation_id: str


class DiagnosticsSummaryResponse(BaseModel):
    events: int = Field(ge=0)
    event_counts: dict[str, int] = Field(default_factory=dict)
    result_states: dict[str, int] = Field(default_factory=dict)
    source_platforms: dict[str, int] = Field(default_factory=dict)
    successes: int = Field(ge=0)
    failures: int = Field(ge=0)
    searches: int = Field(ge=0)
    credible_results: int = Field(ge=0)
    credible_result_rate: float = Field(ge=0, le=1)
    latency_ms: dict[str, float] = Field(default_factory=dict)
    evidence_path_counts: dict[str, int] = Field(default_factory=dict)
    storage: str
    notes: list[str] = Field(default_factory=list)


class BenchmarkCaseResponse(BaseModel):
    case_id: str
    category: str
    passed: bool
    detail: str

class BenchmarkCategoryResponse(BaseModel):
    passed: int = Field(ge=0)
    total: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)

class BenchmarkSummaryResponse(BaseModel):
    passed: int = Field(ge=0)
    total: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    categories: dict[str, BenchmarkCategoryResponse] = Field(default_factory=dict)
    cases: list[BenchmarkCaseResponse] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CandidateURLVerifyResponse(BaseModel):
    candidate_url: HttpUrl
    provider_status: str
    verified: bool
    verification: MultimodalVerifyResponse | None = None
    notes: list[str] = Field(default_factory=list)


class VerificationRankedCandidateResponse(BaseModel):
    candidate: Candidate
    original_score: float = Field(ge=0, le=1)
    adjusted_score: float = Field(ge=0, le=1)
    delta: float
    disposition: Literal["promote", "hold", "demote", "unverified"]
    provider_status: str
    verification: MultimodalVerifyResponse | None = None

class VerificationRerankResponse(BaseModel):
    ranked: list[VerificationRankedCandidateResponse] = Field(default_factory=list)
    verified_count: int = Field(default=0, ge=0)
    provider_attempts: int = Field(default=0, ge=0)
    changed_top_candidate: bool = False
    top_candidate_url: HttpUrl | None = None
    notes: list[str] = Field(default_factory=list)


class BetaReadinessGateResponse(BaseModel):
    gate_id: str
    label: str
    passed: bool
    critical: bool
    detail: str

class BetaReadinessResponse(BaseModel):
    beta_ready: bool
    critical_passed: int = Field(ge=0)
    critical_total: int = Field(ge=0)
    passed: int = Field(ge=0)
    total: int = Field(ge=0)
    benchmark_pass_rate: float = Field(ge=0, le=1)
    gates: list[BetaReadinessGateResponse] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
