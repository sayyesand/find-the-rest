from dataclasses import dataclass

from .models import Candidate

MULTIPART_HINTS = (
    "part 1", "part one", "pt 1", "pt. 1",
    "part 2 coming", "part two coming", "follow for part 2",
    "follow for part two", "continued", "to be continued",
    "what happened next",
)

SUCCESS_STATES = {
    "continuation_found",
    "full_original_found",
    "original_source_found",
    "copies_found",
    "identification_found",
}


@dataclass(frozen=True)
class ResultOutcome:
    state: str
    message: str
    confidence: float
    actions: tuple[str, ...]


def is_success_state(state: str | None) -> bool:
    return bool(state in SUCCESS_STATES)


def _intent_fit(best: Candidate | None) -> float:
    if best is None:
        return 0.0
    try:
        return max(0.0, min(1.0, float(best.evidence.get("intent_fit", 0.0))))
    except (TypeError, ValueError):
        return 0.0


def _related_outcome(intent: str, top: float) -> ResultOutcome:
    by_intent = {
        "continue_story": (
            "I found related material, but not enough evidence to call it the continuation.",
            ("review_related", "find_full_original", "find_other_copies"),
        ),
        "full_original": (
            "I found related material, but not enough evidence to call it the full/original version.",
            ("review_related", "find_original_source", "find_other_copies"),
        ),
        "original_source": (
            "I found related material, but not enough provenance evidence to call it the original source.",
            ("review_related", "find_full_original", "find_other_copies"),
        ),
        "other_copies": (
            "I found related material, but not enough evidence to call it another copy of the same material.",
            ("review_related", "find_original_source", "find_full_original"),
        ),
        "identify_shown": (
            "I found related material, but not enough evidence to identify what is shown.",
            ("review_related", "find_original_source", "share_screenshot"),
        ),
    }
    message, actions = by_intent.get(intent, by_intent["continue_story"])
    return ResultOutcome("related_only", message, min(0.70, top), actions)


def classify_outcome(
    *,
    match_type: str,
    best: Candidate | None,
    candidates: list[Candidate],
    source_text: str,
    cliffhanger_strength: float,
    broad_search_available: bool,
    intent: str = "continue_story",
) -> ResultOutcome:
    fit = _intent_fit(best)

    if best is not None:
        if intent == "continue_story":
            if match_type == "full_original":
                return ResultOutcome(
                    "full_original_found",
                    "I found a likely full/original version.",
                    min(0.99, best.score),
                    ("watch_full_original", "find_continuation", "find_other_copies"),
                )
            if match_type in {"official_continuation", "continuation_repost"}:
                return ResultOutcome(
                    "continuation_found",
                    "I found a credible continuation.",
                    min(0.99, best.score),
                    ("watch_continuation", "find_full_original", "find_other_copies"),
                )

        elif intent == "full_original":
            looks_original = (
                match_type == "full_original"
                or best.trace_role == "likely_original"
                or (fit >= 0.58 and best.trace_score >= 0.28)
            )
            if looks_original:
                return ResultOutcome(
                    "full_original_found",
                    "I found a likely full or complete version.",
                    min(0.99, best.score),
                    ("open_full_original", "find_original_source", "find_other_copies"),
                )

        elif intent == "original_source":
            provenance = max(
                fit,
                best.trace_score if best.trace_role == "likely_original" else 0.0,
                float(best.evidence.get("trace_earlier_upload", 0.0)),
                float(best.evidence.get("trace_creator_authority", 0.0)),
            )
            if best.trace_role == "likely_original" and provenance >= 0.35:
                return ResultOutcome(
                    "original_source_found",
                    "I found a credible candidate for the original source.",
                    min(0.96, best.score),
                    ("open_original_source", "find_full_original", "find_other_copies"),
                )

        elif intent == "other_copies":
            copy_signal = max(
                fit,
                1.0 if best.trace_role == "likely_repost" else 0.0,
                float(best.evidence.get("reverse_image_match", 0.0)),
            )
            if copy_signal >= 0.45:
                return ResultOutcome(
                    "copies_found",
                    "I found a credible alternate copy or repost.",
                    min(0.96, best.score),
                    ("open_copy", "find_original_source", "find_full_original"),
                )

        elif intent == "identify_shown":
            identify_signal = max(
                fit,
                float(best.evidence.get("visible_text_match", 0.0)),
                float(best.evidence.get("reverse_image_match", 0.0)),
                float(best.evidence.get("story_fingerprint", 0.0)),
                float(best.evidence.get("text_similarity", 0.0)),
            )
            if identify_signal >= 0.35:
                return ResultOutcome(
                    "identification_found",
                    "I found a credible source or context match for what is shown.",
                    min(0.94, best.score),
                    ("open_identification", "find_original_source", "find_other_copies"),
                )

    top = candidates[0].score if candidates else 0.0
    related = [c for c in candidates if c.score >= 0.28]
    if related:
        return _related_outcome(intent, top)

    lower = (source_text or "").lower()
    multipart_hint = any(term in lower for term in MULTIPART_HINTS)
    likely_waiting = (
        intent == "continue_story"
        and broad_search_available
        and (multipart_hint or cliffhanger_strength >= 0.72)
    )
    if likely_waiting:
        # This is intentionally probabilistic. Search failure cannot prove non-publication.
        confidence = min(0.68, 0.44 + cliffhanger_strength * 0.22 + (0.08 if multipart_hint else 0.0))
        return ResultOutcome(
            "likely_not_posted_yet",
            "I couldn't verify a continuation. It may not have been posted yet.",
            confidence,
            ("check_later", "find_full_original", "find_other_copies"),
        )

    if not (source_text or "").strip():
        messages = {
            "continue_story": "There isn't enough public context to verify what comes next.",
            "full_original": "There isn't enough public context to verify a full/original version.",
            "original_source": "There isn't enough public context to verify the original source.",
            "other_copies": "There isn't enough public context to verify alternate copies.",
            "identify_shown": "There isn't enough context to identify what is shown.",
        }
        return ResultOutcome(
            "insufficient_context",
            messages.get(intent, messages["continue_story"]),
            0.0,
            ("share_media", "share_screenshot", "try_source_link"),
        )

    failures = {
        "continue_story": (
            "no_verified_match",
            "I couldn't verify a continuation or full original.",
            ("find_full_original", "find_other_copies", "try_source_link"),
        ),
        "full_original": (
            "no_verified_full_original",
            "I couldn't verify a full or complete original version.",
            ("find_original_source", "find_other_copies", "try_source_link"),
        ),
        "original_source": (
            "no_verified_source",
            "I couldn't verify the original source.",
            ("find_full_original", "find_other_copies", "try_source_link"),
        ),
        "other_copies": (
            "no_verified_copy",
            "I couldn't verify another copy or repost.",
            ("find_original_source", "find_full_original", "try_source_link"),
        ),
        "identify_shown": (
            "no_verified_identification",
            "I couldn't verify what is shown from the available clues.",
            ("share_screenshot", "find_original_source", "try_source_link"),
        ),
    }
    state, message, actions = failures.get(intent, failures["continue_story"])
    return ResultOutcome(state, message, 0.0, actions)
