import json
import os
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.Lock()


def _path() -> Path:
    raw = os.getenv("FINDREST_DIAGNOSTICS_PATH", "").strip()
    return Path(raw) if raw else Path("/tmp/findrest-diagnostics.jsonl")


def _max_events() -> int:
    try:
        return max(50, min(int(os.getenv("FINDREST_DIAGNOSTICS_MAX_EVENTS", "1000")), 10000))
    except ValueError:
        return 1000


def record_event(event_type: str, **fields) -> None:
    """Append privacy-safe operational telemetry.

    Callers must pass only coarse operational fields. This module deliberately
    drops keys that could contain raw user content or identifiers.
    """
    blocked = {
        "url", "source_url", "best_match_url", "text", "transcript",
        "ocr", "visible_text", "device_token", "api_key", "snippet", "title",
        "creator", "query", "media", "filename",
    }
    event = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type[:64],
    }
    for key, value in fields.items():
        if key.lower() in blocked:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            if isinstance(value, str):
                value = value[:128]
            event[key] = value
        elif isinstance(value, (list, tuple, set)):
            event[key] = [str(x)[:64] for x in list(value)[:20]]
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        _trim_locked(path)


def _trim_locked(path: Path) -> None:
    max_events = _max_events()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    if len(lines) <= max_events * 2:
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines[-max_events:]) + "\n", encoding="utf-8")
    tmp.replace(path)


def recent_events(limit: int | None = None) -> list[dict]:
    path = _path()
    if not path.exists():
        return []
    max_events = _max_events()
    limit = max(1, min(limit or max_events, max_events))
    with _lock:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
        except Exception:
            return []
    out = []
    for line in lines:
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                out.append(item)
        except Exception:
            continue
    return out


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    idx = min(len(vals)-1, max(0, int(round((len(vals)-1)*q))))
    return vals[idx]


def summary(limit: int | None = None) -> dict:
    events = recent_events(limit)
    counts = Counter(e.get("event_type", "unknown") for e in events)
    states = Counter(e.get("result_state") for e in events if e.get("result_state"))
    platforms = Counter(e.get("source_platform") for e in events if e.get("source_platform"))
    latencies = [
        float(e["latency_ms"]) for e in events
        if isinstance(e.get("latency_ms"), (int, float)) and e["latency_ms"] >= 0
    ]
    successes = sum(1 for e in events if e.get("success") is True)
    failures = sum(1 for e in events if e.get("success") is False)
    searches = [e for e in events if e.get("event_type") in {"analyze", "share_analyze", "media_discovery"}]
    found = sum(1 for e in searches if e.get("result_state") in {"continuation_found", "full_original_found"} or e.get("found") is True)
    evidence = Counter()
    for e in events:
        for key in e.get("evidence_paths", []) or []:
            evidence[str(key)] += 1

    return {
        "events": len(events),
        "event_counts": dict(counts),
        "result_states": dict(states),
        "source_platforms": dict(platforms),
        "successes": successes,
        "failures": failures,
        "searches": len(searches),
        "credible_results": found,
        "credible_result_rate": round(found / len(searches), 4) if searches else 0.0,
        "latency_ms": {
            "p50": round(_percentile(latencies, .50), 1),
            "p95": round(_percentile(latencies, .95), 1),
            "max": round(max(latencies), 1) if latencies else 0.0,
        },
        "evidence_path_counts": dict(evidence),
        "storage": "privacy-safe JSONL",
    }


class timer:
    def __init__(self):
        self.started = time.perf_counter()
    @property
    def ms(self) -> float:
        return (time.perf_counter() - self.started) * 1000.0
