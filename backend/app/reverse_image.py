import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .models import Candidate
from .platforms import detect_platform
from .hunter import canonical_url


@dataclass(frozen=True)
class ReverseImageResult:
    candidate: Candidate
    visual_score: float


def _provider_config() -> tuple[str | None, str | None]:
    endpoint = os.getenv("FINDREST_REVERSE_IMAGE_ENDPOINT", "").strip() or None
    key = os.getenv("FINDREST_REVERSE_IMAGE_KEY", "").strip() or None
    return endpoint, key


def _allowed_hosts() -> set[str]:
    raw = os.getenv("FINDREST_REVERSE_IMAGE_ALLOWED_HOSTS", "").strip()
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _max_response_bytes() -> int:
    try:
        value = int(os.getenv("FINDREST_REVERSE_IMAGE_MAX_RESPONSE_BYTES", str(2 * 1024 * 1024)))
    except ValueError:
        value = 2 * 1024 * 1024
    return max(64 * 1024, min(value, 8 * 1024 * 1024))


def _validate_endpoint(endpoint: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(endpoint)
    except Exception:
        return False, "invalid_endpoint"
    if parsed.scheme != "https" or not parsed.hostname:
        return False, "https_required"
    allowed = _allowed_hosts()
    if allowed and parsed.hostname.lower() not in allowed:
        return False, "host_not_allowed"
    if parsed.username or parsed.password:
        return False, "credentials_in_url_not_allowed"
    return True, "ok"


def configured() -> bool:
    endpoint, _ = _provider_config()
    if not endpoint:
        return False
    ok, _ = _validate_endpoint(endpoint)
    return ok


async def discover_reverse_image(path: str) -> tuple[list[Candidate], list[str]]:
    endpoint, key = _provider_config()
    if not endpoint:
        return [], ["No reverse-image provider is configured."]

    ok, status = _validate_endpoint(endpoint)
    if not ok:
        return [], [f"Reverse-image provider configuration rejected: {status}."]

    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    filename = Path(path).name
    content = Path(path).read_bytes()
    max_response = _max_response_bytes()

    try:
        # Redirects are deliberately disabled so credentials and image bytes cannot
        # be forwarded to an unexpected host.
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=False) as client:
            response = await client.post(
                endpoint,
                headers=headers,
                files={"media": (filename, content, "application/octet-stream")},
            )
            if 300 <= response.status_code < 400:
                return [], ["Reverse-image provider redirect was rejected."]
            response.raise_for_status()

            content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
            if content_type not in {"application/json", "text/json"}:
                return [], ["Reverse-image provider returned an unsupported content type."]

            raw = response.content
            if len(raw) > max_response:
                return [], ["Reverse-image provider response exceeded the configured size limit."]
            payload = response.json()
    except Exception as exc:
        return [], [f"Reverse-image provider request failed: {type(exc).__name__}."]

    raw_results = payload.get("results", []) if isinstance(payload, dict) else []
    merged: dict[str, Candidate] = {}

    for item in raw_results[:40]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        if not url or not title:
            continue
        try:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
        except Exception:
            continue

        score = item.get("score", 0.0)
        try:
            score = float(score)
        except Exception:
            score = 0.0
        score = max(0.0, min(0.99, score))

        platform = item.get("platform") or detect_platform(url)
        if platform not in {"youtube","instagram","facebook","tiktok","x","reddit","web","unknown"}:
            platform = detect_platform(url)

        candidate = Candidate(
            title=title[:500],
            url=url,
            platform=platform,
            creator=(str(item.get("creator")).strip()[:200] if item.get("creator") else None),
            reason="reverse-image provider",
            snippet=(str(item.get("snippet") or "").strip()[:600] or None),
            score=min(0.90, max(0.30, score)),
            evidence={"reverse_image_match": round(score, 4)},
            matched_details={},
        )

        key_url = canonical_url(url)
        previous = merged.get(key_url)
        if previous is None or candidate.score > previous.score:
            merged[key_url] = candidate

    out = sorted(merged.values(), key=lambda c: c.score, reverse=True)[:20]
    notes = [f"Reverse-image provider returned {len(out)} canonical usable candidate(s)."]
    return out, notes
