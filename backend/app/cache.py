import hashlib
import json
import os
import time
from collections import OrderedDict
from typing import Any

_MAX = max(16, min(int(os.getenv("FINDREST_CACHE_MAX_ITEMS", "256")), 2048))
_TTL = max(30, min(int(os.getenv("FINDREST_CACHE_TTL_SECONDS", "900")), 86400))
_store: OrderedDict[str, tuple[float, Any]] = OrderedDict()


def canonical_key(namespace: str, payload: str) -> str:
    digest = hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()
    return f"{namespace}:{digest}"


def media_key(namespace: str, data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()
    return f"{namespace}:{digest}"


def get(key: str):
    item = _store.get(key)
    if item is None:
        return None
    created, value = item
    if time.time() - created > _TTL:
        _store.pop(key, None)
        return None
    _store.move_to_end(key)
    return value


def put(key: str, value: Any) -> None:
    _store[key] = (time.time(), value)
    _store.move_to_end(key)
    while len(_store) > _MAX:
        _store.popitem(last=False)


def stats() -> dict[str, int]:
    now = time.time()
    expired = [k for k, (t, _) in _store.items() if now - t > _TTL]
    for key in expired:
        _store.pop(key, None)
    return {"items": len(_store), "max_items": _MAX, "ttl_seconds": _TTL}
