import re
from dataclasses import dataclass

from .fingerprint import StoryFingerprint
from .matching import clean_text

YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
CAPITALIZED_RE = re.compile(r"\b(?:[A-Z][a-z]{2,})(?:\s+[A-Z][a-z]{2,}){0,2}\b")

GENERIC_NAMES = {
    "Part","Video","Story","Short","Shorts","Update","Full","Original","Official",
    "TikTok","Instagram","Facebook","YouTube","Reddit",
}

@dataclass(frozen=True)
class ContradictionEvidence:
    number_conflict: float = 0.0
    name_conflict: float = 0.0
    missing_anchor: float = 0.0

    @property
    def penalty(self) -> float:
        return min(0.45, self.number_conflict * 0.22 + self.name_conflict * 0.18 + self.missing_anchor * 0.12)

    def as_dict(self) -> dict[str, float]:
        return {
            "number_conflict": round(self.number_conflict, 4),
            "name_conflict": round(self.name_conflict, 4),
            "missing_anchor": round(self.missing_anchor, 4),
            "contradiction_penalty": round(self.penalty, 4),
        }

def _candidate_names(text: str) -> set[str]:
    return {
        x.strip().casefold()
        for x in CAPITALIZED_RE.findall(text or "")
        if x.strip() not in GENERIC_NAMES
    }

def contradiction_evidence(fp: StoryFingerprint, candidate_text: str) -> ContradictionEvidence:
    if not candidate_text:
        return ContradictionEvidence()

    cand_clean = clean_text(candidate_text)
    cand_years = set(YEAR_RE.findall(candidate_text))
    source_years = set(fp.years)

    number_conflict = 0.0
    if source_years and cand_years and source_years.isdisjoint(cand_years):
        number_conflict = 1.0

    source_names = {clean_text(x) for x in fp.names if clean_text(x)}
    cand_names = _candidate_names(candidate_text)
    name_conflict = 0.0
    if source_names and cand_names:
        overlap = {
            s for s in source_names
            if any(s == c or s in c or c in s for c in cand_names)
        }
        if not overlap and len(cand_names) >= 1:
            name_conflict = 0.72 if len(source_names) == 1 else 1.0

    anchors = []
    anchors.extend(clean_text(x) for x in fp.names[:2])
    anchors.extend(fp.numbers[:2])
    anchors.extend(fp.keywords[:4])
    anchors = [a for a in anchors if a]
    missing_anchor = 0.0
    if len(anchors) >= 3:
        hits = sum(1 for a in anchors if a in cand_clean)
        if hits == 0:
            missing_anchor = 1.0
        elif hits == 1:
            missing_anchor = 0.45

    return ContradictionEvidence(number_conflict, name_conflict, missing_anchor)

def apply_contradiction_guard(fp: StoryFingerprint, candidate_text: str, score: float) -> tuple[float, ContradictionEvidence]:
    ev = contradiction_evidence(fp, candidate_text)
    guarded = max(0.0, score - ev.penalty)
    return guarded, ev
