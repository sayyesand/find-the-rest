#!/usr/bin/env python3
"""Invoke Find the Rest's authenticated due-watch batch endpoint.

Designed for Render Cron Jobs and other schedulers. Uses only Python's standard
library, never places credentials in the URL, and exits non-zero on transport,
HTTP, malformed-response, or partial-batch failures.
"""
from __future__ import annotations

import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _endpoint() -> str:
    explicit = os.getenv("FINDREST_SCHEDULER_BASE_URL", "").strip().rstrip("/")
    if explicit:
        if not explicit.startswith(("https://", "http://")):
            raise ValueError("FINDREST_SCHEDULER_BASE_URL must start with http:// or https://")
        return explicit + "/v1/watches/check-due"

    hostport = os.getenv("FINDREST_SCHEDULER_HOSTPORT", "").strip().strip("/")
    if not hostport:
        raise ValueError("Set FINDREST_SCHEDULER_BASE_URL or FINDREST_SCHEDULER_HOSTPORT")
    if "://" in hostport or any(ch.isspace() for ch in hostport):
        raise ValueError("FINDREST_SCHEDULER_HOSTPORT must be a bare host:port value")
    return f"http://{hostport}/v1/watches/check-due"


def _timeout() -> float:
    try:
        value = float(os.getenv("FINDREST_SCHEDULER_TIMEOUT_SECONDS", "120"))
    except ValueError:
        value = 120.0
    return max(10.0, min(value, 300.0))


def run() -> int:
    api_key = os.getenv("FIND_THE_REST_API_KEY", "").strip()
    if not api_key:
        print("scheduler configuration error: FIND_THE_REST_API_KEY is missing", file=sys.stderr)
        return 2

    try:
        endpoint = _endpoint()
    except ValueError as exc:
        print(f"scheduler configuration error: {exc}", file=sys.stderr)
        return 2

    request = Request(
        endpoint,
        data=b"",
        method="POST",
        headers={
            "Accept": "application/json",
            "X-FindTheRest-Key": api_key,
            "User-Agent": "find-the-rest-watch-scheduler/0.45",
        },
    )

    body = None
    for attempt in range(2):
        try:
            with urlopen(request, timeout=_timeout()) as response:
                body = response.read(2_000_000)
                status = getattr(response, "status", 200)
                if not 200 <= status < 300:
                    print(f"scheduler HTTP failure: {status}", file=sys.stderr)
                    return 3
                break
        except HTTPError as exc:
            if exc.code >= 500 and attempt == 0:
                time.sleep(1.0)
                continue
            print(f"scheduler HTTP failure: {exc.code}", file=sys.stderr)
            return 3
        except (URLError, TimeoutError, OSError) as exc:
            if attempt == 0:
                time.sleep(1.0)
                continue
            print(f"scheduler transport failure: {type(exc).__name__}", file=sys.stderr)
            return 3

    try:
        payload = json.loads((body or b"{}").decode("utf-8"))
    except Exception:
        print("scheduler response error: invalid JSON", file=sys.stderr)
        return 4

    if not isinstance(payload, dict):
        print("scheduler response error: expected JSON object", file=sys.stderr)
        return 4

    checked = int(payload.get("checked", 0) or 0)
    found = int(payload.get("found", 0) or 0)
    remaining = int(payload.get("remaining_active", 0) or 0)
    items = payload.get("items") or []
    failures = sum(
        1 for item in items
        if isinstance(item, dict) and item.get("checked") is False
    )

    # Intentionally log only aggregate operational counts. Watch IDs, source URLs,
    # match URLs, and API credentials are never printed by this runner.
    print(
        "watch scheduler complete:"
        f" checked={checked} found={found} failed={failures} remaining_active={remaining}"
    )
    return 5 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run())
