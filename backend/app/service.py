import asyncio
import os
import secrets

from .models import AnalyzeRequest, AnalyzeResponse, Candidate, ProvenanceGraphModel, ProvenanceNodeModel, ProvenanceEdgeModel, SearchCoverageModel
from .platforms import detect_platform
from .discovery import public_metadata
from .hunter import build_search_plans, classify_candidate, merge_ranked
from .source_trace import trace_and_promote
from .fingerprint import fingerprint_story, build_fingerprint_queries, fingerprint_overlap, fingerprint_matches
from .ending import ending_fingerprint, build_ending_queries, ending_boost, ending_matches
from .contradictions import apply_contradiction_guard
from .chain import build_continuation_chain
from .gaps import detect_chain_gaps, build_gap_queries
from .outcome import classify_outcome
from .provenance import build_provenance_graph
from .intent import rank_for_intent
from .confidence import annotate_confidence, confidence_profile
from .matching import credible_continuation, consecutive_numbered_continuation
from .adapters.youtube import extract_video_id, get_video_metadata, normalize_terms, search_candidates, iso8601_duration_seconds
from .adapters.open_web import search_open_web

MIN_MATCH_CONFIDENCE = 0.44
MIN_NUMBERED_CONTINUATION_CONFIDENCE = 0.38

def _query_from_meta(meta: dict) -> str:
    title = meta.get("title") or ""
    desc = meta.get("description") or ""
    creator = meta.get("creator") or ""
    raw = f"{title} {desc} {creator}".strip()
    return " ".join(raw.split()[:24])

async def _hunt_cross_platform(
    *,
    source_url: str,
    source_platform: str,
    source_title: str,
    source_description: str,
    source_creator: str | None,
    scope: str,
    fingerprint_queries: list[str] | None = None,
    source_transcript: str | None = None,
    ending_queries: list[str] | None = None,
    intent: str = "continue_story",
) -> tuple[list[Candidate], dict[str, int | float | bool]]:
    plans = build_search_plans(
        source_platform=source_platform,
        title=source_title,
        description=source_description,
        creator=source_creator,
        scope=scope,
        intent=intent,
    )
    provider_configured = bool(os.getenv("BRAVE_SEARCH_API_KEY", "").strip())
    if (not plans and not fingerprint_queries and not ending_queries) or not provider_configured:
        return [], {
            "provider_configured": provider_configured,
            "attempted": 0,
            "completed": 0,
            "failed": 0,
            "coverage_ratio": 0.0,
        }

    total_budget = max(1, min(int(os.getenv("FIND_THE_REST_MAX_SEARCHES", "7")), 9))
    # Reserve space for the strongest independent search modes whenever available.
    normal_budget = min(len(plans), max(1, total_budget - 4)) if plans else 0
    fp_budget = min(len(fingerprint_queries or []), 3) if fingerprint_queries else 0
    ending_budget = min(len(ending_queries or []), 2) if ending_queries else 0

    while normal_budget + fp_budget + ending_budget > total_budget:
        if normal_budget > 1:
            normal_budget -= 1
        elif fp_budget > 1:
            fp_budget -= 1
        elif ending_budget > 1:
            ending_budget -= 1
        elif normal_budget:
            normal_budget -= 1
        elif fp_budget:
            fp_budget -= 1
        else:
            ending_budget -= 1

    # Fill unused capacity without taking reserved slots away from other modes.
    remaining = total_budget - (normal_budget + fp_budget + ending_budget)
    if remaining > 0 and normal_budget < len(plans):
        add = min(remaining, len(plans) - normal_budget)
        normal_budget += add
        remaining -= add
    if remaining > 0 and fp_budget < len(fingerprint_queries or []):
        add = min(remaining, len(fingerprint_queries or []) - fp_budget)
        fp_budget += add
        remaining -= add
    if remaining > 0 and ending_budget < len(ending_queries or []):
        ending_budget += min(remaining, len(ending_queries or []) - ending_budget)

    tasks = [
        search_open_web(
            plan.query,
            source_url,
            source_title=source_title or (source_transcript[:120] if source_transcript else ""),
            source_description=source_description or (source_transcript[:800] if source_transcript else ""),
            reason_label=plan.label,
        )
        for plan in plans[:normal_budget]
    ]
    for i, query in enumerate((fingerprint_queries or [])[:fp_budget]):
        tasks.append(search_open_web(
            query,
            source_url,
            source_title=source_title or (source_transcript[:120] if source_transcript else ""),
            source_description=source_description or (source_transcript[:800] if source_transcript else ""),
            reason_label=f"story fingerprint {i+1}",
        ))
    for i, query in enumerate((ending_queries or [])[:ending_budget]):
        tasks.append(search_open_web(
            query,
            source_url,
            source_title=source_title or (source_transcript[-160:] if source_transcript else ""),
            source_description=source_description or (source_transcript[-800:] if source_transcript else ""),
            reason_label=f"ending-aware search {i+1}",
        ))

    groups = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[Candidate] = []
    completed = 0
    failed = 0
    for group in groups:
        if isinstance(group, Exception):
            failed += 1
            continue
        completed += 1
        out.extend(group)
    attempted = len(tasks)
    return out, {
        "provider_configured": provider_configured,
        "attempted": attempted,
        "completed": completed,
        "failed": failed,
        "coverage_ratio": round(completed / attempted, 4) if attempted else 0.0,
    }

def _enrich_candidates(candidates, story_fp, ending_fp):
    enriched = []
    for candidate in candidates:
        candidate_text = f"{candidate.title} {candidate.snippet or ''}".strip()
        fp_score = fingerprint_overlap(story_fp, candidate_text)
        ending_score = ending_boost(ending_fp, candidate_text)
        evidence = dict(candidate.evidence)
        evidence["story_fingerprint"] = round(fp_score, 4)
        evidence["ending_continuity"] = round(ending_score, 4)
        evidence["cliffhanger_strength"] = round(ending_fp.cliffhanger_strength, 4)
        boosted = min(0.84, candidate.score + fp_score * 0.14 + ending_score * 0.10)
        guarded, contradiction = apply_contradiction_guard(story_fp, candidate_text, boosted)
        evidence.update(contradiction.as_dict())
        details = dict(candidate.matched_details)
        details.update(fingerprint_matches(story_fp, candidate_text))
        ending_detail = ending_matches(ending_fp, candidate_text)
        if ending_detail:
            details["ending_terms"] = ending_detail
        enriched.append(candidate.model_copy(update={
            "score": guarded,
            "evidence": evidence,
            "matched_details": details,
        }))
    return enriched

async def analyze(req: AnalyzeRequest, *, source_transcript: str | None = None, source_visible_text: str | None = None) -> AnalyzeResponse:
    source_url = str(req.url)
    platform = detect_platform(source_url)
    notes: list[str] = []
    candidates: list[Candidate] = []
    source_creator: str | None = None
    source_title = ""
    source_description = ""
    source_published: str | None = None
    source_duration: float | None = None
    search_coverage = {
        "provider_configured": bool(os.getenv("BRAVE_SEARCH_API_KEY", "").strip()),
        "attempted": 0,
        "completed": 0,
        "failed": 0,
        "coverage_ratio": 0.0,
    }

    if platform == "youtube":
        video_id = extract_video_id(source_url)
        if not video_id:
            notes.append("Could not parse the YouTube video ID.")
        else:
            meta = await get_video_metadata(video_id)
            if meta:
                snip = meta.get("snippet", {})
                source_title = snip.get("title", "")
                source_description = snip.get("description", "")
                source_creator = snip.get("channelTitle")
                source_published = snip.get("publishedAt")
                source_duration = iso8601_duration_seconds(meta.get("contentDetails", {}).get("duration"))
                query = normalize_terms(source_title, source_description)
                channel_id = snip.get("channelId") if req.scope == "creator" else None
                candidates.extend(await search_candidates(
                    query,
                    source_title=source_title,
                    source_description=source_description,
                    source_creator=source_creator,
                    source_published_at=source_published,
                    channel_id=channel_id,
                    limit=18,
                ))
                candidates = [c for c in candidates if video_id not in str(c.url)]
                notes.append("Live YouTube candidates ranked by explainable continuation evidence.")
            else:
                notes.append("Set YOUTUBE_API_KEY to enable live YouTube matching.")
    else:
        meta = await public_metadata(source_url)
        source_title = meta.get("title") or ""
        source_description = meta.get("description") or ""
        source_creator = meta.get("creator")
        if source_title or source_description:
            notes.append(f"Read public {platform.title()} post metadata without logging in or crawling the creator's gallery.")
        else:
            notes.append(f"{platform.title()} link accepted, but that page did not expose usable public metadata.")
        notes.append("Direct creator-gallery search remains provider/API dependent; restricted or private content is never bypassed.")

    fingerprint_description = " ".join(x for x in [source_description, source_visible_text or ""] if x).strip()
    # On social share pages, generic login/page metadata (for example,
    # "Log into Facebook") must not override the user's specific caption clue.
    source_identity_text = source_visible_text or source_title or source_description

    # Facebook and Instagram commonly expose little or no public page metadata.
    # A user-supplied caption/clue can still seed a public YouTube search without
    # logging in, scraping private content, or requiring another paid provider.
    if platform != "youtube" and os.getenv("YOUTUBE_API_KEY", "").strip():
        if source_visible_text:
            clue_text = " ".join(
                x for x in [source_visible_text, source_transcript or ""] if x
            ).strip()
        else:
            clue_text = " ".join(
                x for x in [source_title, source_description, source_transcript or ""] if x
            ).strip()
        query = normalize_terms(source_identity_text, clue_text)
        if query:
            candidates.extend(await search_candidates(
                query,
                source_title=source_identity_text,
                source_description=clue_text,
                source_creator=source_creator,
                source_published_at=source_published,
                channel_id=None,
                limit=18,
            ))
            notes.append("Used the supplied public caption or story clue to search YouTube for matching continuations.")

    story_fp = fingerprint_story(source_title, fingerprint_description, source_transcript)
    fingerprint_queries = build_fingerprint_queries(story_fp, source_creator)
    ending_fp = ending_fingerprint(source_transcript, f"{source_title} {source_description}")
    ending_queries = build_ending_queries(ending_fp)

    if source_transcript:
        notes.append("Story fingerprint includes spoken words transcribed from the user-shared source video.")
    if source_visible_text:
        notes.append("Story fingerprint includes visible text extracted from user-shared media.")

    if req.scope in {"social", "web"} and (source_title or source_description or source_transcript or source_visible_text):
        hunt_result = await _hunt_cross_platform(
            source_url=source_url,
            source_platform=platform,
            source_title=source_title,
            source_description=fingerprint_description,
            source_creator=source_creator,
            scope=req.scope,
            fingerprint_queries=fingerprint_queries,
            source_transcript=source_transcript,
            ending_queries=ending_queries,
            intent=req.intent,
        )
        if isinstance(hunt_result, tuple) and len(hunt_result) == 2:
            cross, search_coverage = hunt_result
        else:
            # Backward compatibility for injected/custom hunters written before v0.47.
            cross = hunt_result
            search_coverage = {
                "provider_configured": bool(os.getenv("BRAVE_SEARCH_API_KEY", "").strip()),
                "attempted": 0,
                "completed": 0,
                "failed": 0,
                "coverage_ratio": 0.0,
            }
        candidates.extend(cross)
        if os.getenv("BRAVE_SEARCH_API_KEY", "").strip():
            notes.append("Cross-platform candidate hunter searched continuation, repost, full-original, story-fingerprint, and ending-aware paths across supported public sources.")
        else:
            notes.append("Set BRAVE_SEARCH_API_KEY to activate cross-platform candidate hunting.")

    candidates = merge_ranked(_enrich_candidates(candidates, story_fp, ending_fp), source_creator)
    candidates = trace_and_promote(
        candidates,
        source_creator=source_creator,
        source_duration=source_duration,
        source_published=source_published,
    )
    candidates = [annotate_confidence(c) for c in rank_for_intent(candidates, req.intent)[:12]]
    continuation_chain, chain_confidence = build_continuation_chain(candidates)

    # Self-heal obvious numbered gaps such as Part 2 -> Part 4.
    gaps = detect_chain_gaps(continuation_chain)
    recovered_parts: list[int] = []
    if gaps and os.getenv("BRAVE_SEARCH_API_KEY", "").strip():
        gap_queries = build_gap_queries(
            gaps,
            source_title=source_title,
            source_description=source_description,
            creator=source_creator,
            fingerprint_terms=story_fp.all_terms(),
        )
        recovered_raw: list[Candidate] = []
        for missing_part, query in gap_queries:
            found = await search_open_web(
                query,
                source_url,
                source_title=source_title or (source_transcript[:120] if source_transcript else ""),
                source_description=source_description or (source_transcript[:800] if source_transcript else ""),
                reason_label=f"missing Part {missing_part} recovery",
            )
            # Stricter prefilter: only candidates explicitly mentioning the missing part.
            for candidate in found:
                text = f"{candidate.title} {candidate.snippet or ''}".lower()
                if f"part {missing_part}" in text or f"pt {missing_part}" in text or f"pt. {missing_part}" in text:
                    recovered_raw.append(candidate)
        if recovered_raw:
            recovered = _enrich_candidates(recovered_raw, story_fp, ending_fp)
            recovered = [c for c in recovered if c.score >= 0.50 and c.evidence.get("contradiction_penalty", 0.0) < 0.28]
            if recovered:
                candidates = merge_ranked(candidates + recovered, source_creator)
                candidates = trace_and_promote(
                    candidates,
                    source_creator=source_creator,
                    source_duration=source_duration,
                    source_published=source_published,
                )
                candidates = [annotate_confidence(c) for c in rank_for_intent(candidates, req.intent)[:12]]
                continuation_chain, chain_confidence = build_continuation_chain(candidates)
                recovered_parts = sorted({
                    n.inferred_part for n in continuation_chain
                    if n.inferred_part is not None and any(g.missing_part == n.inferred_part for g in gaps)
                })

    if gaps:
        missing_labels = ", ".join(f"Part {g.missing_part}" for g in gaps)
        if recovered_parts:
            notes.append("Chain gap recovery filled: " + ", ".join(f"Part {p}" for p in recovered_parts) + ".")
        still_missing = [g.missing_part for g in detect_chain_gaps(continuation_chain)]
        if still_missing:
            notes.append("Chain still has unresolved gap(s): " + ", ".join(f"Part {p}" for p in still_missing) + ".")

    top_profile = confidence_profile(candidates[0]) if candidates else None
    best = None
    for candidate in candidates:
        profile = confidence_profile(candidate)
        clears_general_threshold = profile.calibrated >= MIN_MATCH_CONFIDENCE
        clears_numbered_threshold = (
            profile.calibrated >= MIN_NUMBERED_CONTINUATION_CONFIDENCE
            and consecutive_numbered_continuation(
                source_title=source_identity_text,
                source_creator=source_creator,
                candidate=candidate,
            )
        )
        if not (clears_general_threshold or clears_numbered_threshold):
            continue
        if req.intent == "continue_story" and not credible_continuation(
            source_title=source_identity_text,
            source_creator=source_creator,
            candidate=candidate,
        ):
            continue
        best = candidate
        break

    if candidates and best is None and req.intent == "continue_story":
        notes.append(
            "Related results were rejected as continuations because they lacked shared story identity or a credible next-part sequence."
        )

    if continuation_chain:
        numbered = [n for n in continuation_chain if n.inferred_part is not None]
        if numbered:
            notes.append(f"Continuation chain assembled with {len(continuation_chain)} credible node(s); explicit parts are ordered numerically.")
        else:
            notes.append(f"Continuation chain assembled with {len(continuation_chain)} credible node(s) using relationship and publication evidence.")

    if best:
        kind = classify_candidate(source_creator, best)
        if best.trace_role == "likely_original":
            kind = "full_original"
        if kind == "full_original":
            match_type = "full_original"
        elif kind == "official_continuation":
            match_type = "official_continuation"
        else:
            match_type = "continuation_repost"
        profile = confidence_profile(best)
        confidence = profile.calibrated
        notes.append(f"Best candidate classified as {kind.replace('_', ' ')}.")
        notes.append(
            f"Confidence calibration: {profile.grade}; {profile.family_count} independent evidence family/families, "
            f"{profile.strong_family_count} strong."
        )
        if best.trace_role:
            notes.append(f"Source tracing role: {best.trace_role.replace('_', ' ')} ({best.trace_score:.0%} originality evidence).")
    else:
        match_type = "no_match"
        confidence = 0.0
        if candidates:
            profile = confidence_profile(candidates[0])
            notes.append(
                f"Top candidate raw score {candidates[0].score:.0%}; calibrated confidence {profile.calibrated:.0%}, "
                f"below the {MIN_MATCH_CONFIDENCE:.0%} acceptance threshold."
            )

    provenance = build_provenance_graph(
        source_url=str(req.url),
        source_creator=source_creator,
        source_published_at=source_published,
        candidates=candidates,
    )
    provenance_model = ProvenanceGraphModel(
        nodes=[
            ProvenanceNodeModel(
                node_id=n.node_id,
                label=n.label,
                url=n.url,
                role=n.role,
                score=n.score,
                creator=n.creator,
                published_at=n.published_at,
            )
            for n in provenance.nodes
        ],
        edges=[
            ProvenanceEdgeModel(
                from_id=e.from_id,
                to_id=e.to_id,
                relationship=e.relationship,
                confidence=e.confidence,
                reasons=list(e.reasons),
            )
            for e in provenance.edges
        ],
        likely_origin_node_id=provenance.likely_origin_node_id,
        confidence=provenance.confidence,
    )
    if provenance.edges:
        notes.append(f"Source-lineage graph inferred {len(provenance.edges)} relationship(s) across {len(provenance.nodes)} node(s).")

    outcome = classify_outcome(
        match_type=match_type,
        best=best,
        candidates=candidates,
        source_text=" ".join(x for x in [source_title, source_description, source_transcript or "", source_visible_text or ""] if x),
        cliffhanger_strength=ending_fp.cliffhanger_strength,
        broad_search_available=(
            search_coverage["provider_configured"]
            and search_coverage["completed"] >= 3
            and search_coverage["coverage_ratio"] >= 0.60
        ),
        intent=req.intent,
    )
    broad_enough = (
        search_coverage["provider_configured"]
        and search_coverage["completed"] >= 3
        and search_coverage["coverage_ratio"] >= 0.60
    )
    if search_coverage["attempted"]:
        notes.append(
            f"Public search coverage: {search_coverage['completed']}/{search_coverage['attempted']} planned searches completed "
            f"({search_coverage['coverage_ratio']:.0%})."
        )
    elif search_coverage["provider_configured"]:
        notes.append("Public search provider was configured, but no broad-search plans were executed for this source.")
    else:
        notes.append("No public broad-search provider was configured.")
    if not broad_enough:
        notes.append("Search coverage was not broad enough to support a 'likely not posted yet' hint.")
    notes.append(f"Search intent: {req.intent.replace('_', ' ')}. Intent changes query/ranking priority but never overrides weak evidence.")
    notes.append("Result state is probabilistic; a failed public search does not prove that a continuation does not exist.")
    notes.append("Metadata-only matches remain capped below 85% until media/semantic continuity is verified.")
    return AnalyzeResponse(
        search_id=secrets.token_hex(8),
        search_intent=req.intent,
        source_platform=platform,
        source_url=req.url,
        match_type=match_type,
        confidence=confidence,
        confidence_grade=(confidence_profile(best).grade if best else (top_profile.grade if top_profile else "low")),
        evidence_family_count=(confidence_profile(best).family_count if best else (top_profile.family_count if top_profile else 0)),
        strong_evidence_family_count=(confidence_profile(best).strong_family_count if best else (top_profile.strong_family_count if top_profile else 0)),
        best_match=best,
        candidates=candidates,
        continuation_chain=continuation_chain,
        chain_confidence=chain_confidence,
        missing_parts=[g.missing_part for g in detect_chain_gaps(continuation_chain)],
        recovered_parts=recovered_parts,
        result_state=outcome.state,
        result_message=outcome.message,
        result_state_confidence=(min(outcome.confidence, confidence) if best else outcome.confidence),
        available_actions=list(outcome.actions),
        provenance_graph=provenance_model,
        search_coverage=SearchCoverageModel(
            provider_configured=bool(search_coverage["provider_configured"]),
            attempted=int(search_coverage["attempted"]),
            completed=int(search_coverage["completed"]),
            failed=int(search_coverage["failed"]),
            coverage_ratio=float(search_coverage["coverage_ratio"]),
            broad_enough_for_nonpublication_hint=broad_enough,
        ),
        notes=notes,
    )
