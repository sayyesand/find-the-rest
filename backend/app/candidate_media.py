import os
import ipaddress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class CandidateMediaFetch:
    path: str | None
    status: str
    content_type: str | None = None
    bytes_written: int = 0


def _endpoint() -> str | None:
    return os.getenv("FINDREST_CANDIDATE_MEDIA_ENDPOINT", "").strip() or None


def _allowed_hosts() -> set[str]:
    raw = os.getenv("FINDREST_CANDIDATE_MEDIA_ALLOWED_HOSTS", "").strip()
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _max_bytes() -> int:
    try:
        value = int(os.getenv("FINDREST_CANDIDATE_MEDIA_MAX_BYTES", str(60 * 1024 * 1024)))
    except ValueError:
        value = 60 * 1024 * 1024
    return max(1_000_000, min(value, 120 * 1024 * 1024))


def _validate_endpoint(endpoint: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(endpoint)
    except Exception:
        return False, "invalid_endpoint"
    if parsed.scheme != "https" or not parsed.hostname:
        return False, "https_required"
    if parsed.username or parsed.password:
        return False, "credentials_in_url_not_allowed"
    allowed = _allowed_hosts()
    if allowed and parsed.hostname.lower() not in allowed:
        return False, "host_not_allowed"
    return True, "ok"


def _validate_candidate_url(candidate_url: str) -> bool:
    try:
        parsed = urlparse(candidate_url)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or host == "localhost"
        or host.endswith(".localhost")
    ):
        return False
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return True
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def configured() -> bool:
    endpoint = _endpoint()
    if not endpoint:
        return False
    ok, _ = _validate_endpoint(endpoint)
    return ok


async def fetch_permitted_candidate_media(candidate_url: str, workdir: str) -> CandidateMediaFetch:
    """Fetch candidate media only through a deployment-configured licensed/permitted gateway.

    Find the Rest never directly downloads arbitrary social URLs here. The gateway
    is responsible for authorization, provider terms, and returning only media the
    deployment is permitted to process.
    """
    endpoint = _endpoint()
    if not endpoint:
        return CandidateMediaFetch(None, "provider_not_configured")

    endpoint_ok, endpoint_status = _validate_endpoint(endpoint)
    if not endpoint_ok:
        return CandidateMediaFetch(None, f"provider_config_invalid_{endpoint_status}")

    if not _validate_candidate_url(candidate_url):
        return CandidateMediaFetch(None, "invalid_candidate_url")

    key = os.getenv("FINDREST_CANDIDATE_MEDIA_KEY", "").strip()
    headers = {"Accept": "video/mp4,video/quicktime,video/x-m4v,application/octet-stream"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    try:
        # Redirects are deliberately disabled so the authorization header and
        # candidate URL cannot be forwarded to an unexpected host.
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            response = await client.post(
                endpoint,
                headers=headers,
                json={"candidate_url": candidate_url},
            )
    except Exception:
        return CandidateMediaFetch(None, "provider_error")

    if 300 <= response.status_code < 400:
        return CandidateMediaFetch(None, "provider_redirect_rejected")
    if response.status_code == 404:
        return CandidateMediaFetch(None, "candidate_unavailable")
    if not (200 <= response.status_code < 300):
        return CandidateMediaFetch(None, f"provider_http_{response.status_code}")

    content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    allowed_types = {
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/x-m4v": ".m4v",
        "application/octet-stream": ".mp4",
    }
    suffix = allowed_types.get(content_type)
    if suffix is None:
        return CandidateMediaFetch(None, "unsupported_content_type", content_type=content_type)

    max_bytes = _max_bytes()
    length_header = response.headers.get("content-length")
    if length_header:
        try:
            declared = int(length_header)
        except ValueError:
            return CandidateMediaFetch(None, "invalid_content_length", content_type=content_type)
        if declared < 0:
            return CandidateMediaFetch(None, "invalid_content_length", content_type=content_type)
        if declared > max_bytes:
            return CandidateMediaFetch(None, "media_too_large", content_type=content_type)

    content = response.content
    if not content:
        return CandidateMediaFetch(None, "empty_media", content_type=content_type)
    if len(content) > max_bytes:
        return CandidateMediaFetch(None, "media_too_large", content_type=content_type)

    target = Path(workdir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    out = (target / f"candidate{suffix}").resolve()
    # Keep the write inside the caller-provided temporary directory.
    if target not in out.parents:
        return CandidateMediaFetch(None, "unsafe_output_path", content_type=content_type)
    out.write_bytes(content)
    return CandidateMediaFetch(str(out), "ok", content_type=content_type, bytes_written=len(content))
