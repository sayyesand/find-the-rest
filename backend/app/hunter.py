import re
from dataclasses import dataclass
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

from .models import Candidate
from .platforms import detect_platform
from .matching import clean_text, creator_similarity, continuation_signal

SOCIAL_DOMAINS = {
    "youtube": ("youtube.com", "youtu.be"),
    "instagram": ("instagram.com",),
    "facebook": ("facebook.com", "fb.watch"),
    "tiktok": ("tiktok.com",),
    "x": ("x.com", "twitter.com"),
    "reddit": ("reddit.com",),
}

TRACKING_KEYS = {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","fbclid","gclid","si","feature"}

@dataclass(frozen=True)
class SearchPlan:
    label: str
    query: str
    target_platform: str | None = None
    intent: str = "continuation"

def canonical_url(url: str) -> str:
    p = urlparse(url)
    host = (p.hostname or "").lower().removeprefix("www.")
    path = re.sub(r"/+$", "", p.path) or "/"
    kept = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False) if k.lower() not in TRACKING_KEYS]
    return urlunparse(("https", host, path, "", urlencode(sorted(kept)), ""))

def compact_seed(title: str, description: str, creator: str | None = None, max_words: int = 14) -> str:
    raw = clean_text(f"{title} {description}")
    words = []
    seen = set()
    for word in raw.split():
        if word in seen or len(word) < 3:
            continue
        seen.add(word)
        words.append(word)
        if len(words) >= max_words:
            break
    if creator:
        c = " ".join(clean_text(creator).split()[:3])
        if c and c not in " ".join(words):
            words.extend(c.split())
    return " ".join(words)

def build_search_plans(
    *, source_platform: str, title: str, description: str, creator: str | None, scope: str,
    intent: str = "continue_story",
) -> list[SearchPlan]:
    seed = compact_seed(title, description, creator)
    if not seed:
        return []
    by_intent = {
        "continue_story": [
            SearchPlan("direct continuation", f'"{seed}" ("part 2" OR continued OR continuation OR "what happened next")'),
            SearchPlan("full original", f'"{seed}" ("full video" OR original OR uncut OR complete)', intent="original"),
            SearchPlan("repost/mirror", f'"{seed}" (repost OR mirror OR source)', intent="repost"),
        ],
        "full_original": [
            SearchPlan("full original", f'"{seed}" ("full video" OR "full version" OR uncut OR complete)', intent="original"),
            SearchPlan("original source", f'"{seed}" ("original source" OR original creator)', intent="original"),
            SearchPlan("direct continuation", f'"{seed}" ("part 2" OR continued)'),
        ],
        "original_source": [
            SearchPlan("original source", f'"{seed}" ("original source" OR "original creator" OR credited)', intent="original"),
            SearchPlan("full original", f'"{seed}" ("full video" OR original OR uncut)', intent="original"),
            SearchPlan("repost/source trail", f'"{seed}" (repost OR mirror OR source OR via)', intent="repost"),
        ],
        "other_copies": [
            SearchPlan("repost/mirror", f'"{seed}" (repost OR mirror OR copy OR source)', intent="repost"),
            SearchPlan("full original", f'"{seed}" ("full video" OR original)', intent="original"),
            SearchPlan("direct continuation", f'"{seed}" ("part 2" OR continued)'),
        ],
        "identify_shown": [
            SearchPlan("identify/context", f'"{seed}" (who OR what OR where OR source)'),
            SearchPlan("original source", f'"{seed}" ("original source" OR original)', intent="original"),
            SearchPlan("related coverage", f'"{seed}" (article OR report OR video)'),
        ],
    }
    plans = by_intent.get(intent, by_intent["continue_story"])
    if scope in {"social", "web"}:
        for platform, domains in SOCIAL_DOMAINS.items():
            if platform == source_platform:
                continue
            site_clause = " OR ".join(f"site:{d}" for d in domains)
            plans.append(SearchPlan(
                f"{platform} continuation",
                f'({site_clause}) "{seed}" ("part 2" OR continued OR continuation)',
                target_platform=platform,
            ))
    # Bound provider cost: 3 general + up to 6 cross-platform queries.
    return plans[:9]

def classify_candidate(source_creator: str | None, candidate: Candidate) -> str:
    raw = f"{candidate.title} {candidate.snippet or ''} {candidate.reason}"
    text = clean_text(raw)
    same_creator = creator_similarity(source_creator, candidate.creator) >= 0.92
    continuation = continuation_signal(candidate.title, f"{candidate.snippet or ''} {candidate.reason}")
    if any(x in text for x in ("full original", "original source", "complete video", "uncut")):
        return "full_original"
    if same_creator and continuation >= 0.72:
        return "official_continuation"
    if same_creator:
        return "official_related"
    if continuation >= 0.72:
        return "continuation_repost"
    return "related_repost"

def merge_ranked(candidates: list[Candidate], source_creator: str | None = None) -> list[Candidate]:
    best: dict[str, Candidate] = {}
    for c in candidates:
        key = canonical_url(str(c.url))
        previous = best.get(key)
        if previous is None or c.score > previous.score:
            best[key] = c
    # Give slight preference to exact same-creator results, but never enough to
    # overwhelm a materially stronger cross-platform match.
    def adjusted(c: Candidate) -> float:
        bonus = 0.025 if creator_similarity(source_creator, c.creator) >= 0.92 else 0.0
        return min(1.0, c.score + bonus)
    return sorted(best.values(), key=adjusted, reverse=True)
