import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx

_lock = threading.Lock()


def _path() -> Path:
    raw = os.getenv("FINDREST_PUSH_STORE_PATH", "").strip()
    return Path(raw) if raw else Path("/tmp/findrest-push.json")


def _load() -> dict[str, dict]:
    path = _path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict[str, dict]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8", errors="ignore")).hexdigest()[:16]


def register_device(installation_id: str, token: str, environment: str = "sandbox") -> dict:
    record = {
        "installation_id": installation_id,
        "device_token": token,
        "token_fingerprint": token_fingerprint(token),
        "environment": environment,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "active": True,
        "last_event_key": None,
    }
    with _lock:
        data = _load()
        data[installation_id] = record
        _save(data)
    return {k: v for k, v in record.items() if k != "device_token"}


def unregister_device(installation_id: str) -> bool:
    with _lock:
        data = _load()
        record = data.get(installation_id)
        if not record:
            return False
        record["active"] = False
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        data[installation_id] = record
        _save(data)
    return True


def get_device(installation_id: str | None) -> dict | None:
    if not installation_id:
        return None
    with _lock:
        record = _load().get(installation_id)
    return record if record and record.get("active") else None


def _mark_event(installation_id: str, event_key: str) -> None:
    with _lock:
        data = _load()
        record = data.get(installation_id)
        if not record:
            return
        record["last_event_key"] = event_key
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        data[installation_id] = record
        _save(data)


async def send_found_notification(
    *,
    installation_id: str | None,
    watch_id: str,
    result_state: str,
    best_match_url: str | None,
) -> tuple[bool, str]:
    """Send through a deployment-configured APNs gateway.

    Contract: POST JSON to FINDREST_PUSH_ENDPOINT with bearer auth when
    FINDREST_PUSH_KEY is configured. The gateway owns Apple APNs credentials.
    """
    device = get_device(installation_id)
    if not device:
        return False, "no_registered_device"

    event_key = hashlib.sha256(
        f"{watch_id}|{result_state}|{best_match_url or ''}".encode()
    ).hexdigest()[:24]
    if device.get("last_event_key") == event_key:
        return False, "duplicate_suppressed"

    endpoint = os.getenv("FINDREST_PUSH_ENDPOINT", "").strip()
    if not endpoint:
        return False, "push_provider_not_configured"

    payload = {
        "device_token": device["device_token"],
        "environment": device.get("environment", "sandbox"),
        "title": "Find the Rest found it",
        "body": "A credible continuation or full original is now available.",
        "data": {
            "watch_id": watch_id,
            "result_state": result_state,
            "best_match_url": best_match_url,
        },
    }
    headers = {"Content-Type": "application/json"}
    key = os.getenv("FINDREST_PUSH_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
        if 200 <= response.status_code < 300:
            _mark_event(installation_id, event_key)
            return True, "sent"
        return False, f"provider_http_{response.status_code}"
    except Exception:
        return False, "provider_error"
