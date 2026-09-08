from .models import Candidate
from .matching import clean_text, continuation_signal

INTENTS = {"continue_story","full_original","original_source","other_copies","identify_shown"}

def intent_fit(candidate: Candidate, intent: str) -> float:
    text = clean_text(f"{candidate.title} {candidate.snippet or ''} {candidate.reason}")
    if intent == "continue_story":
        return max(
            continuation_signal(candidate.title, candidate.snippet or ""),
            candidate.evidence.get("continuation_signal", 0.0),
            candidate.evidence.get("ending_continuity", 0.0),
        )
    if intent == "full_original":
        explicit = 1.0 if any(x in text for x in ("full video","full original","complete video","uncut","entire video","full version")) else 0.0
        return max(explicit, candidate.trace_score if candidate.trace_role == "likely_original" else 0.0)
    if intent == "original_source":
        original = candidate.trace_score if candidate.trace_role == "likely_original" else 0.0
        earlier = candidate.evidence.get("trace_earlier_upload", 0.0)
        authority = candidate.evidence.get("trace_creator_authority", 0.0)
        return min(1.0, original * .55 + earlier * .25 + authority * .20)
    if intent == "other_copies":
        repost = 1.0 if candidate.trace_role == "likely_repost" else 0.0
        visual = candidate.evidence.get("reverse_image_match", 0.0)
        return max(repost, visual, candidate.evidence.get("text_similarity", 0.0) * .55)
    if intent == "identify_shown":
        return max(
            candidate.evidence.get("story_fingerprint", 0.0),
            candidate.evidence.get("visible_text_match", 0.0),
            candidate.evidence.get("reverse_image_match", 0.0),
            candidate.evidence.get("text_similarity", 0.0),
        )
    return 0.0

def rank_for_intent(candidates: list[Candidate], intent: str) -> list[Candidate]:
    if intent not in INTENTS:
        intent = "continue_story"
    decorated=[]
    for c in candidates:
        fit=intent_fit(c,intent)
        ev=dict(c.evidence); ev["intent_fit"]=round(fit,4)
        updated=c.model_copy(update={"evidence":ev})
        # Intent is a tie-breaker/close-contest signal; it cannot rescue a weak match.
        utility=c.score + min(.12, fit*.12)
        decorated.append((utility,c.score,updated))
    decorated.sort(key=lambda x:(x[0],x[1]), reverse=True)
    return [x[2] for x in decorated]
