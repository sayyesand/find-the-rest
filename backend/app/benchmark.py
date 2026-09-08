from dataclasses import dataclass
from typing import Callable

from .chain import build_continuation_chain, infer_episode, infer_part
from .contradictions import apply_contradiction_guard
from .fingerprint import fingerprint_story
from .hunter import canonical_url, classify_candidate, merge_ranked
from .models import Candidate
from .outcome import classify_outcome


@dataclass(frozen=True)
class BenchmarkResult:
    case_id: str
    category: str
    passed: bool
    detail: str


def _candidate(
    title: str,
    url: str,
    *,
    creator: str | None = None,
    score: float = .6,
    snippet: str | None = None,
    evidence: dict[str, float] | None = None,
    trace_role: str | None = None,
    published_at: str | None = None,
) -> Candidate:
    return Candidate(
        title=title,
        url=url,
        platform="web",
        creator=creator,
        score=score,
        reason="benchmark fixture",
        snippet=snippet,
        evidence=evidence or {},
        trace_role=trace_role,
        published_at=published_at,
    )


def run_benchmark() -> list[BenchmarkResult]:
    cases: list[BenchmarkResult] = []

    # 1. Fake Part 2 label should be materially penalized when the story anchors conflict.
    fp = fingerprint_story(
        "Maya rescued an injured owl",
        "Maya drove the owl to Cedar Ridge Wildlife Center in 2024.",
        None,
    )
    guarded, ev = apply_contradiction_guard(
        fp,
        "PART 2: Jordan rescues a fox at Harbor Bay Aquarium in 2021.",
        .82,
    )
    cases.append(BenchmarkResult(
        "fake-part2-conflicting-story",
        "false_positive",
        ev.penalty >= .20 and guarded <= .62,
        f"penalty={ev.penalty:.3f}, guarded={guarded:.3f}",
    ))

    # 2. Same creator alone must not imply continuation.
    same_creator = _candidate(
        "My new garden tour",
        "https://example.com/garden",
        creator="Maya Lee",
        score=.74,
    )
    classification = classify_candidate("Maya Lee", same_creator)
    cases.append(BenchmarkResult(
        "same-creator-unrelated-video",
        "false_positive",
        classification == "official_related",
        f"classification={classification}",
    ))

    # 3. Explicit Part 2 from same creator should classify as official continuation.
    official = _candidate(
        "Owl rescue Part 2",
        "https://example.com/owl2",
        creator="Maya Lee",
        score=.78,
    )
    classification = classify_candidate("Maya Lee", official)
    cases.append(BenchmarkResult(
        "official-part2",
        "positive",
        classification == "official_continuation",
        f"classification={classification}",
    ))

    # 4. A repost labelled Part 2 can be continuation evidence without becoming official.
    repost = _candidate(
        "Owl rescue Part 2 continued",
        "https://mirror.example/owl2",
        creator="Clip Archive",
        score=.70,
    )
    classification = classify_candidate("Maya Lee", repost)
    cases.append(BenchmarkResult(
        "continuation-repost",
        "repost",
        classification == "continuation_repost",
        f"classification={classification}",
    ))

    # 5. Full original wording should outrank continuation semantics as original-source intent.
    full = _candidate(
        "Full original uncut owl rescue",
        "https://example.com/full",
        creator="Maya Lee",
        score=.77,
        trace_role="likely_original",
    )
    cases.append(BenchmarkResult(
        "full-original",
        "provenance",
        classify_candidate("Maya Lee", full) == "full_original",
        "full-original classification",
    ))

    # 6. Episode numbers must not be misread as Part numbers.
    episode = _candidate("Episode 248 — Draupadi weds the Pandavas", "https://example.com/e248")
    cases.append(BenchmarkResult(
        "episode-is-not-part",
        "ordering",
        infer_episode(episode) == 248 and infer_part(episode) is None,
        f"episode={infer_episode(episode)}, part={infer_part(episode)}",
    ))

    # 7. Duplicate explicit parts should keep the stronger candidate.
    weak = _candidate(
        "Story Part 2", "https://weak.example/p2", creator="Archive",
        score=.53, evidence={"continuation_signal": .8, "story_fingerprint": .42},
    )
    strong = _candidate(
        "Story Part 2", "https://strong.example/p2", creator="Maya Lee",
        score=.79, evidence={"continuation_signal": .9, "story_fingerprint": .82, "creator_match": 1.0},
    )
    chain, _ = build_continuation_chain([weak, strong])
    cases.append(BenchmarkResult(
        "duplicate-part-keep-strongest",
        "ordering",
        len(chain) == 1 and str(chain[0].candidate.url) == "https://strong.example/p2",
        f"selected={str(chain[0].candidate.url) if chain else 'none'}",
    ))

    # 8. Tracking variants must canonicalize to one result.
    merged = merge_ranked([
        _candidate("Same clip", "https://example.com/watch?v=7&utm_source=a", score=.55),
        _candidate("Same clip better", "https://example.com/watch?utm_campaign=b&v=7", score=.71),
    ])
    cases.append(BenchmarkResult(
        "tracking-variant-dedupe",
        "repost",
        len(merged) == 1 and merged[0].score == .71,
        f"merged={len(merged)}, score={merged[0].score if merged else 0}",
    ))

    # 9. Canonical URLs should remove social tracking but retain meaningful query parameters.
    canon = canonical_url("http://www.example.com/watch?v=7&utm_source=x&fbclid=abc")
    cases.append(BenchmarkResult(
        "canonical-url-keeps-content-id",
        "provenance",
        canon == "https://example.com/watch?v=7",
        f"canonical={canon}",
    ))

    # 10. Related material must not be promoted to a verified continuation.
    related = _candidate("Wildlife center tour", "https://example.com/tour", score=.39)
    outcome = classify_outcome(
        match_type="no_match",
        best=None,
        candidates=[related],
        source_text="Maya rescued an injured owl",
        cliffhanger_strength=.1,
        broad_search_available=True,
    )
    cases.append(BenchmarkResult(
        "related-only-is-not-continuation",
        "no_answer",
        outcome.state == "related_only",
        f"state={outcome.state}",
    ))

    # 11. No context should explicitly return insufficient context.
    outcome = classify_outcome(
        match_type="no_match",
        best=None,
        candidates=[],
        source_text="",
        cliffhanger_strength=0,
        broad_search_available=True,
    )
    cases.append(BenchmarkResult(
        "empty-context",
        "no_answer",
        outcome.state == "insufficient_context",
        f"state={outcome.state}",
    ))

    # 12. A clear multipart cliffhanger with a broad but empty search is probabilistic, not proof.
    outcome = classify_outcome(
        match_type="no_match",
        best=None,
        candidates=[],
        source_text="Part 1 — follow for Part 2",
        cliffhanger_strength=.82,
        broad_search_available=True,
    )
    cases.append(BenchmarkResult(
        "not-posted-is-probabilistic",
        "no_answer",
        outcome.state == "likely_not_posted_yet" and outcome.confidence <= .68,
        f"state={outcome.state}, confidence={outcome.confidence:.3f}",
    ))

    # 13. Without broad search coverage, failure must not claim likely-not-posted.
    outcome = classify_outcome(
        match_type="no_match",
        best=None,
        candidates=[],
        source_text="Part 1 — follow for Part 2",
        cliffhanger_strength=.82,
        broad_search_available=False,
    )
    cases.append(BenchmarkResult(
        "no-search-no-publication-claim",
        "no_answer",
        outcome.state == "no_verified_match",
        f"state={outcome.state}",
    ))

    # 14. Roman numerals should remain usable for multipart chains.
    roman = _candidate("The mystery continues — Part IV", "https://example.com/p4")
    cases.append(BenchmarkResult(
        "roman-part-number",
        "ordering",
        infer_part(roman) == 4,
        f"part={infer_part(roman)}",
    ))


    # 15. "Part 2" label with weak story support must not become a strong accepted match.
    fp = fingerprint_story(
        "Lena finds an antique camera in Santa Fe",
        "She discovers a roll of undeveloped film inside the camera.",
        None,
    )
    guarded, ev = apply_contradiction_guard(
        fp,
        "PART 2: Jordan reviews a new smartphone camera at a trade show in 2021.",
        .70,
    )
    cases.append(BenchmarkResult(
        "part2-label-cannot-rescue-story-drift",
        "false_positive",
        guarded < .60,
        f"guarded={guarded:.3f}, penalty={ev.penalty:.3f}",
    ))

    # 16. A later upload labelled original should not automatically defeat earlier provenance.
    fake_original = _candidate(
        "ORIGINAL FULL VIDEO",
        "https://archive.example/later",
        creator="ClipArchive",
        score=.68,
        trace_role="likely_repost",
        published_at="2026-08-10T00:00:00Z",
        evidence={"trace_earlier_upload": 0.0, "trace_creator_authority": .1},
    )
    cases.append(BenchmarkResult(
        "original-label-is-not-provenance",
        "provenance",
        fake_original.trace_role == "likely_repost" and fake_original.evidence.get("trace_earlier_upload", 0) == 0,
        f"role={fake_original.trace_role}",
    ))

    # 17. Similar title, same creator, and high score still cannot substitute for continuation wording.
    sibling = _candidate(
        "Owl rescue behind the scenes",
        "https://example.com/behind",
        creator="Maya Lee",
        score=.80,
        snippet="How we filmed the rescue",
    )
    cases.append(BenchmarkResult(
        "same-creator-similar-topic-not-continuation",
        "false_positive",
        classify_candidate("Maya Lee", sibling) == "official_related",
        f"classification={classify_candidate('Maya Lee', sibling)}",
    ))

    # 18. Intent mismatch: original-source search must not return continuation success language.
    generic = _candidate(
        "Owl Rescue Part 2",
        "https://example.com/p2-original-intent",
        creator="Maya Lee",
        score=.76,
        evidence={"intent_fit": .08},
    )
    outcome = classify_outcome(
        match_type="official_continuation",
        best=generic,
        candidates=[generic],
        source_text="owl rescue",
        cliffhanger_strength=.8,
        broad_search_available=True,
        intent="original_source",
    )
    cases.append(BenchmarkResult(
        "intent-mismatch-no-false-success",
        "intent",
        outcome.state == "related_only",
        f"state={outcome.state}",
    ))

    # 19. Non-continuation intents must never emit likely-not-posted-yet.
    outcome = classify_outcome(
        match_type="no_match",
        best=None,
        candidates=[],
        source_text="Part 1 — follow for Part 2",
        cliffhanger_strength=.9,
        broad_search_available=True,
        intent="identify_shown",
    )
    cases.append(BenchmarkResult(
        "identify-intent-no-publication-hint",
        "intent",
        outcome.state != "likely_not_posted_yet",
        f"state={outcome.state}",
    ))

    # 20. Tracking variants with reordered meaningful params remain one canonical candidate.
    merged = merge_ranked([
        _candidate("Clip", "https://example.com/watch?b=2&a=1&utm_source=x", score=.62),
        _candidate("Clip mirror", "https://www.example.com/watch?a=1&b=2", score=.69),
    ])
    cases.append(BenchmarkResult(
        "query-order-dedupe",
        "repost",
        len(merged) == 1 and merged[0].score == .69,
        f"merged={len(merged)}",
    ))

    # 21. Weak related results should remain related and never become a success state.
    weak_related = _candidate(
        "Wildlife Center Donations",
        "https://example.com/donate",
        score=.30,
        evidence={"intent_fit": .05},
    )
    outcome = classify_outcome(
        match_type="no_match",
        best=None,
        candidates=[weak_related],
        source_text="owl rescue",
        cliffhanger_strength=.0,
        broad_search_available=True,
        intent="full_original",
    )
    cases.append(BenchmarkResult(
        "weak-related-stays-related",
        "no_answer",
        outcome.state == "related_only",
        f"state={outcome.state}",
    ))

    # 22. Strong copy evidence should produce copy-specific success rather than generic continuation.
    copy = _candidate(
        "Reposted rescue clip",
        "https://mirror.example/rescue-copy",
        creator="MirrorChannel",
        score=.72,
        trace_role="likely_repost",
        evidence={"intent_fit": .88, "reverse_image_match": .84},
    )
    outcome = classify_outcome(
        match_type="no_match",
        best=copy,
        candidates=[copy],
        source_text="owl rescue",
        cliffhanger_strength=.1,
        broad_search_available=True,
        intent="other_copies",
    )
    cases.append(BenchmarkResult(
        "copy-intent-specific-success",
        "intent",
        outcome.state == "copies_found",
        f"state={outcome.state}",
    ))

    # 23. Identify-shown needs actual clue support, not merely a high generic score.
    high_generic = _candidate(
        "Popular viral clip",
        "https://example.com/viral",
        score=.82,
        evidence={"intent_fit": .08},
    )
    outcome = classify_outcome(
        match_type="no_match",
        best=high_generic,
        candidates=[high_generic],
        source_text="unknown machine",
        cliffhanger_strength=0,
        broad_search_available=True,
        intent="identify_shown",
    )
    cases.append(BenchmarkResult(
        "identify-requires-identification-evidence",
        "intent",
        outcome.state == "related_only",
        f"state={outcome.state}",
    ))

    return cases


def benchmark_summary() -> dict:
    cases = run_benchmark()
    categories: dict[str, dict[str, int | float]] = {}
    for case in cases:
        bucket = categories.setdefault(case.category, {"passed": 0, "total": 0, "pass_rate": 0.0})
        bucket["total"] += 1
        if case.passed:
            bucket["passed"] += 1
    for bucket in categories.values():
        bucket["pass_rate"] = round(bucket["passed"] / bucket["total"], 4) if bucket["total"] else 0.0

    passed = sum(1 for c in cases if c.passed)
    total = len(cases)
    return {
        "passed": passed,
        "total": total,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "categories": categories,
        "cases": [
            {
                "case_id": c.case_id,
                "category": c.category,
                "passed": c.passed,
                "detail": c.detail,
            }
            for c in cases
        ],
    }
