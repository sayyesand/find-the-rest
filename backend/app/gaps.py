from dataclasses import dataclass

from .models import ChainNode
from .matching import clean_text

@dataclass(frozen=True)
class ChainGap:
    missing_part: int
    before_part: int | None
    after_part: int | None

def detect_chain_gaps(chain: list[ChainNode], *, max_part: int = 20) -> list[ChainGap]:
    parts = sorted({n.inferred_part for n in chain if n.inferred_part is not None and n.inferred_part <= max_part})
    if len(parts) < 2:
        return []
    gaps: list[ChainGap] = []
    present = set(parts)
    for p in range(parts[0], parts[-1] + 1):
        if p in present:
            continue
        before = max((x for x in parts if x < p), default=None)
        after = min((x for x in parts if x > p), default=None)
        gaps.append(ChainGap(p, before, after))
    return gaps[:4]

def build_gap_queries(
    gaps: list[ChainGap],
    *,
    source_title: str,
    source_description: str,
    creator: str | None,
    fingerprint_terms: list[str],
) -> list[tuple[int, str]]:
    seed_words = []
    for w in clean_text(f"{source_title} {source_description}").split():
        if len(w) >= 4 and w not in seed_words:
            seed_words.append(w)
        if len(seed_words) >= 5:
            break
    if not seed_words:
        seed_words = [clean_text(x) for x in fingerprint_terms[:4] if clean_text(x)]
    creator_clause = f'"{creator}" ' if creator else ""
    seed = " ".join(seed_words[:5])
    out = []
    for gap in gaps:
        if not seed and not creator_clause:
            continue
        q = f'{creator_clause}{seed} ("part {gap.missing_part}" OR "pt {gap.missing_part}")'
        out.append((gap.missing_part, q.strip()))
    return out[:4]
