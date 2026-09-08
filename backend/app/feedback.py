import json
import os
import threading
import hashlib
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.Lock()

def _path() -> Path:
    raw = os.getenv("FINDREST_FEEDBACK_PATH", "").strip()
    return Path(raw) if raw else Path("/tmp/findrest-feedback.jsonl")

def record_feedback(payload: dict) -> None:
    event = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "search_id": payload.get("search_id"),
        "verdict": payload.get("verdict"),
        "best_match_fingerprint": hashlib.sha256(str(payload.get("best_match_url") or "").encode("utf-8")).hexdigest()[:16] if payload.get("best_match_url") else None,
        "source_platform": payload.get("source_platform"),
        "confidence": payload.get("confidence"),
    }
    line = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
