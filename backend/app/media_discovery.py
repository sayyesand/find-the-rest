import asyncio
import os

from .adapters.open_web import search_open_web
from .hunter import merge_ranked, canonical_url
from .models import Candidate
from .visible_text import VisibleTextEvidence, visible_text_queries
from .fingerprint import fingerprint_story, fingerprint_matches, fingerprint_overlap
from .reverse_image import discover_reverse_image
from .vision_clues import extract_visual_clues, clue_queries, clue_overlap


async def discover_from_media(path: str, ev: VisibleTextEvidence, visual_clues=None) -> tuple[list[Candidate], list[str]]:
    notes: list[str] = []

    ocr_candidates: list[Candidate] = []
    queries = visible_text_queries(ev, limit=5)
    if queries and os.getenv("BRAVE_SEARCH_API_KEY", "").strip():
        source_creator = ev.handles[0].lstrip("@") if ev.handles else None
        source_title = " ".join(ev.keywords[:6])
        source_description = ev.text[:1400]
        fp = fingerprint_story(source_title, source_description)

        tasks = [
            search_open_web(
                q,
                "https://findtherest.invalid/shared-media",
                source_title=source_title,
                source_description=source_description,
                reason_label=f"visible-text clue {i+1}",
            )
            for i, q in enumerate(queries)
        ]
        groups = await asyncio.gather(*tasks, return_exceptions=True)

        candidates: list[Candidate] = []
        for group in groups:
            if isinstance(group, Exception):
                continue
            candidates.extend(group)

        enriched: list[Candidate] = []
        for c in candidates:
            candidate_text = f"{c.title} {c.snippet or ''}".strip()
            fp_score = fingerprint_overlap(fp, candidate_text)
            evidence = dict(c.evidence)
            evidence["visible_text_match"] = round(fp_score, 4)
            score = min(0.84, c.score + fp_score * 0.18)
            details = dict(c.matched_details)
            details.update(fingerprint_matches(fp, candidate_text))
            if source_creator and c.creator and source_creator.casefold() == c.creator.casefold():
                evidence["visible_handle_match"] = 1.0
                score = min(0.84, score + 0.08)
                details["handles"] = ["@" + source_creator]
            enriched.append(c.model_copy(update={
                "score": score,
                "evidence": evidence,
                "matched_details": details,
            }))
        ocr_candidates = merge_ranked(enriched, source_creator)[:12]
        notes.append(f"Standalone screenshot discovery searched {len(queries)} visible-text clue path(s).")
    elif queries:
        notes.append("Visible-text clues were found, but BRAVE_SEARCH_API_KEY is not configured.")
    else:
        notes.append("No sufficiently distinctive visible-text clues were found for OCR-based web discovery.")

    if visual_clues is None:
        visual_clues = await extract_visual_clues(path)
    visual_candidates: list[Candidate] = []
    vqueries = clue_queries(visual_clues, limit=5)
    if vqueries and os.getenv("BRAVE_SEARCH_API_KEY", "").strip():
        tasks = [
            search_open_web(
                q,
                "https://findtherest.invalid/shared-media",
                source_title=" ".join(visual_clues.logos[:2] + visual_clues.objects[:3]),
                source_description=" ".join(visual_clues.scenes[:3] + visual_clues.clothing[:3]),
                reason_label=f"visual clue {i+1}",
            )
            for i, q in enumerate(vqueries)
        ]
        groups = await asyncio.gather(*tasks, return_exceptions=True)
        raw_visual=[]
        for group in groups:
            if not isinstance(group, Exception):
                raw_visual.extend(group)
        for c in raw_visual:
            score, matches = clue_overlap(visual_clues, f"{c.title} {c.snippet or ''}")
            evidence=dict(c.evidence)
            evidence["visual_clue_match"]=round(score,4)
            details=dict(c.matched_details)
            for key, values in matches.items():
                if values:
                    details[key]=values
            visual_candidates.append(c.model_copy(update={
                "score": min(.84, c.score + score*.14),
                "evidence": evidence,
                "matched_details": details,
            }))
        visual_candidates=merge_ranked(visual_candidates)[:12]
        notes.append(f"Visual object/logo/scene clues searched {len(vqueries)} web clue path(s).")
    elif visual_clues.provider_status == "ok":
        notes.append("Visual object/logo/scene clues were extracted, but open-web search is not configured.")
    elif visual_clues.local_scene_tags:
        notes.append("Local coarse scene tags were extracted; semantic object/logo recognition requires the optional visual-clue provider.")

    reverse_candidates, reverse_notes = await discover_reverse_image(path)
    notes.extend(reverse_notes)

    # Fuse OCR, semantic visual clues, and reverse-image results by canonical URL.
    # while combining independent evidence from duplicate discoveries.
    merged: dict[str, Candidate] = {}
    for c in ocr_candidates + visual_candidates + reverse_candidates:
        key = canonical_url(str(c.url))
        previous = merged.get(key)
        if previous is None:
            merged[key] = c
            continue
        evidence = dict(previous.evidence)
        evidence.update(c.evidence)
        details = dict(previous.matched_details)
        for k, vals in c.matched_details.items():
            details[k] = list(dict.fromkeys(details.get(k, []) + vals))
        score = max(previous.score, c.score)
        # Independent OCR + reverse-image agreement gets a small, capped boost.
        independent = sum(
            1 for key in ("visible_text_match", "visual_clue_match", "reverse_image_match")
            if evidence.get(key, 0) > 0
        )
        if independent >= 2:
            score = min(0.94, score + min(.10, .04 * independent))
            evidence["multimodal_agreement"] = 1.0
        chosen = previous if previous.score >= c.score else c
        merged[key] = chosen.model_copy(update={
            "score": score,
            "evidence": evidence,
            "matched_details": details,
        })

    ranked = sorted(merged.values(), key=lambda c: c.score, reverse=True)[:12]
    if ranked:
        notes.append("OCR and reverse-image evidence were fused into a single candidate ranking.")
    return ranked, notes


async def discover_from_visible_text(ev: VisibleTextEvidence) -> tuple[list[Candidate], list[str]]:
    """Backward-compatible OCR-only helper used by tests/older callers."""
    queries = visible_text_queries(ev, limit=5)
    if not queries:
        return [], ["No sufficiently distinctive visible-text clues were found for standalone web discovery."]
    if not os.getenv("BRAVE_SEARCH_API_KEY", "").strip():
        return [], ["Set BRAVE_SEARCH_API_KEY to activate standalone screenshot discovery."]

    source_creator = ev.handles[0].lstrip("@") if ev.handles else None
    source_title = " ".join(ev.keywords[:6])
    source_description = ev.text[:1400]
    fp = fingerprint_story(source_title, source_description)
    tasks = [
        search_open_web(
            q,
            "https://findtherest.invalid/shared-media",
            source_title=source_title,
            source_description=source_description,
            reason_label=f"visible-text clue {i+1}",
        )
        for i, q in enumerate(queries)
    ]
    groups = await asyncio.gather(*tasks, return_exceptions=True)
    candidates: list[Candidate] = []
    for group in groups:
        if not isinstance(group, Exception):
            candidates.extend(group)
    enriched = []
    for c in candidates:
        candidate_text = f"{c.title} {c.snippet or ''}".strip()
        fp_score = fingerprint_overlap(fp, candidate_text)
        evidence = dict(c.evidence)
        evidence["visible_text_match"] = round(fp_score, 4)
        score = min(0.84, c.score + fp_score * 0.18)
        details = dict(c.matched_details)
        details.update(fingerprint_matches(fp, candidate_text))
        enriched.append(c.model_copy(update={"score": score, "evidence": evidence, "matched_details": details}))
    ranked = merge_ranked(enriched, source_creator)[:12]
    notes = [f"Standalone screenshot discovery searched {len(queries)} visible-text clue path(s)."] if ranked else []
    return ranked, notes
