import re
from collections import Counter
from dataclasses import dataclass

from .matching import clean_text, tokens

CAPITALIZED_RE = re.compile(r"\b(?:[A-Z][a-z]{2,})(?:\s+[A-Z][a-z]{2,}){0,2}\b")
QUOTED_RE = re.compile(r'["“](.{4,80}?)[”"]')
NUMBER_RE = re.compile(r"\b\d{2,4}\b")

COMMON = {
    "video","part","story","short","shorts","people","thing","things","really","just","like",
    "today","yesterday","tomorrow","someone","something","anything","everything","happened",
}

@dataclass(frozen=True)
class StoryFingerprint:
    names: tuple[str, ...]
    phrases: tuple[str, ...]
    keywords: tuple[str, ...]
    numbers: tuple[str, ...]
    years: tuple[str, ...] = ()

    def all_terms(self) -> list[str]:
        out: list[str] = []
        out.extend(self.names)
        out.extend(self.phrases)
        out.extend(self.numbers)
        out.extend(self.keywords)
        return out

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "names": list(self.names),
            "phrases": list(self.phrases),
            "keywords": list(self.keywords),
            "numbers": list(self.numbers),
            "years": list(self.years),
        }

def _unique_keep_order(items):
    seen=set()
    out=[]
    for item in items:
        k=item.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(item)
    return out

def fingerprint_story(title: str = "", description: str = "", transcript: str | None = None) -> StoryFingerprint:
    raw = " ".join(x for x in (title, description, transcript or "") if x).strip()
    if not raw:
        return StoryFingerprint((),(),(),(),())

    names = [
        x.strip() for x in CAPITALIZED_RE.findall(raw)
        if x.lower() not in COMMON and len(x.split()) <= 3
    ]
    names = _unique_keep_order(names)[:5]

    quoted = [_clean_phrase(x) for x in QUOTED_RE.findall(raw)]
    quoted = [x for x in quoted if 4 <= len(x) <= 80]
    quoted = _unique_keep_order(quoted)[:4]

    clean = clean_text(raw)
    ws = [w for w in clean.split() if len(w) >= 4 and w not in COMMON]
    counts = Counter(ws)
    # Distinctive-ish terms: reward rarer/nonrepeated words over boilerplate.
    keywords = []
    for w, count in counts.most_common():
        if w in COMMON:
            continue
        if w not in keywords:
            keywords.append(w)
        if len(keywords) >= 10:
            break

    # Phrase windows around the strongest keywords make search useful even if titles differ.
    phrases = list(quoted)
    words = clean.split()
    for kw in keywords[:5]:
        try:
            i = words.index(kw)
        except ValueError:
            continue
        start=max(0,i-2); end=min(len(words),i+3)
        p=" ".join(words[start:end])
        if len(p.split()) >= 3:
            phrases.append(p)
    phrases=_unique_keep_order(phrases)[:6]

    numbers=_unique_keep_order(NUMBER_RE.findall(raw))[:4]
    years=tuple(_unique_keep_order(re.findall(r"\b(?:19|20)\d{2}\b", raw))[:4])
    return StoryFingerprint(tuple(names), tuple(phrases), tuple(keywords), tuple(numbers), years)

def _clean_phrase(s: str) -> str:
    return re.sub(r"\s+"," ",s).strip(" \t\n\r'\"")

def build_fingerprint_queries(fp: StoryFingerprint, creator: str | None = None) -> list[str]:
    terms = fp.all_terms()
    if not terms:
        return []
    q=[]
    if fp.names and fp.phrases:
        q.append(f'"{fp.names[0]}" "{fp.phrases[0]}"')
    if fp.phrases:
        q.append(f'"{fp.phrases[0]}"')
    if len(fp.keywords) >= 4:
        q.append(" ".join(f'"{x}"' for x in fp.keywords[:4]))
    if fp.numbers and fp.keywords:
        q.append(f'"{fp.numbers[0]}" ' + " ".join(fp.keywords[:3]))
    if creator and fp.keywords:
        q.append(f'"{creator}" ' + " ".join(fp.keywords[:4]))
    return _unique_keep_order(q)[:5]

def fingerprint_overlap(fp: StoryFingerprint, candidate_text: str) -> float:
    cand = clean_text(candidate_text)
    if not cand:
        return 0.0
    cand_tokens = set(cand.split())
    scored=[]
    for name in fp.names:
        scored.append(1.0 if clean_text(name) in cand else 0.0)
    for phrase in fp.phrases:
        p=clean_text(phrase)
        scored.append(1.0 if p and p in cand else 0.0)
    for number in fp.numbers:
        scored.append(1.0 if number in cand_tokens else 0.0)
    for kw in fp.keywords[:8]:
        scored.append(1.0 if kw in cand_tokens else 0.0)
    if not scored:
        return 0.0
    # Require multiple details when possible; a single generic overlap is weak evidence.
    hits=sum(scored)
    raw=hits/len(scored)
    return min(1.0, raw * 1.25 if hits >= 2 else raw * 0.55)


def fingerprint_matches(fp: StoryFingerprint, candidate_text: str) -> dict[str, list[str]]:
    cand = clean_text(candidate_text)
    cand_tokens = set(cand.split())
    details: dict[str, list[str]] = {}

    names = [name for name in fp.names if clean_text(name) and clean_text(name) in cand]
    phrases = [phrase for phrase in fp.phrases if clean_text(phrase) and clean_text(phrase) in cand]
    numbers = [number for number in fp.numbers if number in cand_tokens]
    keywords = [kw for kw in fp.keywords[:10] if kw in cand_tokens]

    if names: details["names"] = names[:5]
    if phrases: details["phrases"] = phrases[:5]
    if numbers: details["numbers"] = numbers[:4]
    if keywords: details["keywords"] = keywords[:8]
    return details
