import hashlib
import json
import os
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.Lock()

_ALLOWED_VERDICTS = {"correct", "wrong", "not_enough_information"}
_ALLOWED_GRADES = {"high", "moderate", "tentative", "low"}
_ALLOWED_INTENTS = {"continue_story", "full_original", "original_source", "other_copies", "identify_shown"}

def _path() -> Path:
    raw = os.getenv("FINDREST_FEEDBACK_CASES_PATH", "").strip()
    return Path(raw) if raw else Path("/tmp/findrest-feedback-cases.jsonl")

def _max_cases() -> int:
    try:
        return max(50, min(int(os.getenv("FINDREST_FEEDBACK_CASES_MAX", "2000")), 20000))
    except ValueError:
        return 2000

def _bucket(value: float | None) -> str:
    if value is None:
        return "unknown"
    try:
        v = max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return "unknown"
    if v >= .80: return "80-100"
    if v >= .60: return "60-79"
    if v >= .40: return "40-59"
    if v >= .20: return "20-39"
    return "0-19"

def _short_hash(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

def make_case(payload: dict) -> dict:
    verdict = str(payload.get("verdict") or "")
    if verdict not in _ALLOWED_VERDICTS:
        verdict = "not_enough_information"

    grade = str(payload.get("confidence_grade") or "low")
    if grade not in _ALLOWED_GRADES:
        grade = "low"

    intent = str(payload.get("search_intent") or "continue_story")
    if intent not in _ALLOWED_INTENTS:
        intent = "continue_story"

    family_count = payload.get("evidence_family_count")
    strong_count = payload.get("strong_evidence_family_count")
    try: family_count = max(0, min(int(family_count or 0), 20))
    except (TypeError, ValueError): family_count = 0
    try: strong_count = max(0, min(int(strong_count or 0), 20))
    except (TypeError, ValueError): strong_count = 0

    # The case signature contains only coarse labels and hashes. It deliberately
    # excludes source URLs, candidate URLs, titles, creators, queries, transcripts,
    # OCR, screenshots, video, filenames, and free-form user text.
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "case_id": _short_hash(str(payload.get("search_id") or "")),
        "verdict": verdict,
        "source_platform": str(payload.get("source_platform") or "unknown")[:24],
        "search_intent": intent,
        "result_state": str(payload.get("result_state") or "unknown")[:40],
        "confidence_bucket": _bucket(payload.get("confidence")),
        "confidence_grade": grade,
        "evidence_family_count": family_count,
        "strong_evidence_family_count": strong_count,
        "best_match_fingerprint": _short_hash(str(payload.get("best_match_url") or "")),
    }

def record_case(payload: dict) -> dict:
    case = make_case(payload)
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(case, separators=(",", ":"), ensure_ascii=False)
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        _trim_locked(path)
    return case

def _trim_locked(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    max_cases = _max_cases()
    if len(lines) <= max_cases * 2:
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines[-max_cases:]) + "\n", encoding="utf-8")
    tmp.replace(path)

def recent_cases(limit: int | None = None) -> list[dict]:
    path = _path()
    if not path.exists():
        return []
    max_cases = _max_cases()
    limit = max(1, min(limit or max_cases, max_cases))
    with _lock:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
        except Exception:
            return []
    out=[]
    for line in lines:
        try:
            item=json.loads(line)
            if isinstance(item, dict):
                out.append(item)
        except Exception:
            continue
    return out

def summary(limit: int | None = None) -> dict:
    cases = recent_cases(limit)
    verdicts = Counter(c.get("verdict", "unknown") for c in cases)
    failures = [c for c in cases if c.get("verdict") in {"wrong", "not_enough_information"}]

    patterns = Counter()
    for c in failures:
        key = (
            c.get("source_platform", "unknown"),
            c.get("search_intent", "continue_story"),
            c.get("result_state", "unknown"),
            c.get("confidence_grade", "low"),
            c.get("confidence_bucket", "unknown"),
        )
        patterns[key] += 1

    top_patterns = [
        {
            "source_platform": k[0],
            "search_intent": k[1],
            "result_state": k[2],
            "confidence_grade": k[3],
            "confidence_bucket": k[4],
            "count": count,
        }
        for k, count in patterns.most_common(12)
    ]

    high_conf_wrong = sum(
        1 for c in cases
        if c.get("verdict") == "wrong"
        and c.get("confidence_grade") in {"high", "moderate"}
        and c.get("confidence_bucket") in {"60-79", "80-100"}
    )

    return {
        "cases": len(cases),
        "verdict_counts": dict(verdicts),
        "failure_cases": len(failures),
        "high_confidence_wrong": high_conf_wrong,
        "top_failure_patterns": top_patterns,
        "storage": "privacy-safe hashed/coarse JSONL",
    }
