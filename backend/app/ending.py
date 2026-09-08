import re
from dataclasses import dataclass

from .matching import clean_text, tokens

CLIFFHANGER_PATTERNS = (
    "but then", "until", "when suddenly", "and then", "what happened next",
    "you won't believe", "you will not believe", "before he could", "before she could",
    "that's when", "that is when", "the next thing", "suddenly",
)

@dataclass(frozen=True)
class EndingFingerprint:
    tail_text: str
    tail_terms: tuple[str, ...]
    cliffhanger_strength: float

def ending_fingerprint(transcript: str | None, fallback_text: str = "", tail_words: int = 44) -> EndingFingerprint:
    raw = (transcript or fallback_text or "").strip()
    if not raw:
        return EndingFingerprint("", (), 0.0)
    raw_words = raw.split()
    raw_tail = " ".join(raw_words[-tail_words:])
    words = re.findall(r"[A-Za-z0-9']+", raw_tail)
    tail = " ".join(words)
    cleaned = clean_text(tail)
    terms = [w for w in cleaned.split() if len(w) >= 4]
    # Preserve order, remove duplicates, emphasize the very end.
    seen=set(); ordered=[]
    for w in terms:
        if w not in seen:
            seen.add(w); ordered.append(w)
    ordered = ordered[-12:]

    lower = tail.lower()
    strength = 0.0
    if any(p in lower for p in CLIFFHANGER_PATTERNS):
        strength = 0.8
    if raw_tail.rstrip().endswith("?"):
        strength = max(strength, 0.72)
    if re.search(r"\b(?:but|until|when|then|suddenly)\b.{0,24}$", lower):
        strength = max(strength, 0.62)
    return EndingFingerprint(tail, tuple(ordered), strength)

def build_ending_queries(fp: EndingFingerprint) -> list[str]:
    if not fp.tail_terms:
        return []
    terms=list(fp.tail_terms)
    queries=[]
    if len(terms) >= 5:
        queries.append(" ".join(f'"{x}"' for x in terms[-5:]))
    if len(terms) >= 3:
        seed = " ".join(terms[-3:])
        queries.append(seed + ' "continued"')
        queries.append(seed + ' "part 2"')
        queries.append(seed + ' "update"')
    if fp.tail_text:
        tail_words=clean_text(fp.tail_text).split()
        if len(tail_words) >= 7:
            phrase=" ".join(tail_words[-7:])
            queries.append(f'"{phrase}"')
    # Stable unique order.
    out=[]; seen=set()
    for q in queries:
        if q not in seen:
            seen.add(q); out.append(q)
    return out[:5]

def ending_overlap(fp: EndingFingerprint, candidate_text: str) -> float:
    if not fp.tail_terms:
        return 0.0
    cand=set(clean_text(candidate_text).split())
    terms=list(fp.tail_terms)
    weighted_total=0.0
    hit_total=0.0
    n=len(terms)
    for i, term in enumerate(terms):
        # Later tail terms receive more weight.
        weight=0.65 + 0.35 * ((i+1)/n)
        weighted_total += weight
        if term in cand:
            hit_total += weight
    if weighted_total <= 0:
        return 0.0
    base=hit_total/weighted_total
    if hit_total > 0 and len(cand.intersection(set(terms[-5:]))) >= 2:
        base *= 1.2
    return min(1.0, base)

def ending_boost(fp: EndingFingerprint, candidate_text: str) -> float:
    overlap=ending_overlap(fp, candidate_text)
    # A cliffhanger makes the ending more diagnostic, but ending evidence remains secondary.
    multiplier=1.0 + 0.22 * fp.cliffhanger_strength
    return min(1.0, overlap * multiplier)


def ending_matches(fp: EndingFingerprint, candidate_text: str) -> list[str]:
    if not fp.tail_terms:
        return []
    cand = set(clean_text(candidate_text).split())
    return [term for term in fp.tail_terms if term in cand][-8:]
