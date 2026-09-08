import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .hunter import canonical_url

_lock = threading.RLock()


def _path() -> Path:
    raw = os.getenv("FINDREST_WATCH_DB_PATH", "").strip()
    if not raw:
        raw = os.getenv("FINDREST_WATCH_PATH", "").strip()
    return Path(raw) if raw else Path("/tmp/findrest-watches.sqlite3")


def _legacy_json(path: Path) -> dict[str, dict] | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _connect() -> sqlite3.Connection:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Seamless migration from the v0.27-v0.37 JSON store. Keep a backup beside it.
    legacy = _legacy_json(path)
    if legacy is not None:
        backup = path.with_suffix(path.suffix + ".legacy-json")
        if not backup.exists():
            path.replace(backup)
        else:
            path.unlink(missing_ok=True)
    else:
        legacy = None

    conn = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watches (
            watch_id TEXT PRIMARY KEY,
            source_url TEXT NOT NULL,
            scope TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_checked_at TEXT,
            last_result_state TEXT,
            last_best_match_url TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            installation_id TEXT,
            intent TEXT NOT NULL DEFAULT 'continue_story'
        )
    """)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(watches)").fetchall()}
    if "intent" not in columns:
        conn.execute("ALTER TABLE watches ADD COLUMN intent TEXT NOT NULL DEFAULT 'continue_story'")

    conn.execute("DROP INDEX IF EXISTS idx_watches_active_source_scope")
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_watches_active_source_scope_intent
        ON watches(source_url, scope, intent)
        WHERE active = 1
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_watches_due
        ON watches(active, last_checked_at, created_at)
    """)

    if legacy:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for watch in legacy.values():
                if not isinstance(watch, dict) or not watch.get("watch_id") or not watch.get("source_url"):
                    continue
                conn.execute("""
                    INSERT OR IGNORE INTO watches (
                        watch_id, source_url, scope, created_at, last_checked_at,
                        last_result_state, last_best_match_url, active, installation_id, intent
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    watch["watch_id"],
                    canonical_url(str(watch["source_url"])),
                    watch.get("scope", "web"),
                    watch.get("created_at") or datetime.now(timezone.utc).isoformat(),
                    watch.get("last_checked_at"),
                    watch.get("last_result_state"),
                    watch.get("last_best_match_url"),
                    1 if watch.get("active", True) else 0,
                    watch.get("installation_id"),
                    watch.get("intent", "continue_story"),
                ))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            conn.close()
            raise

    return conn


def _row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    out = dict(row)
    out["active"] = bool(out["active"])
    return out


def create_watch(source_url: str, scope: str = "web", installation_id: str | None = None, intent: str = "continue_story") -> dict:
    source_url = canonical_url(source_url)
    now = datetime.now(timezone.utc).isoformat()
    with _lock, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            existing = conn.execute(
                "SELECT * FROM watches WHERE active=1 AND source_url=? AND scope=? AND intent=? LIMIT 1",
                (source_url, scope, intent),
            ).fetchone()
            if existing:
                if installation_id and existing["installation_id"] != installation_id:
                    conn.execute(
                        "UPDATE watches SET installation_id=? WHERE watch_id=?",
                        (installation_id, existing["watch_id"]),
                    )
                    existing = conn.execute(
                        "SELECT * FROM watches WHERE watch_id=?", (existing["watch_id"],)
                    ).fetchone()
                conn.execute("COMMIT")
                return _row(existing)

            watch_id = secrets.token_hex(8)
            conn.execute("""
                INSERT INTO watches (
                    watch_id, source_url, scope, created_at, active, installation_id, intent
                ) VALUES (?, ?, ?, ?, 1, ?, ?)
            """, (watch_id, source_url, scope, now, installation_id, intent))
            created = conn.execute(
                "SELECT * FROM watches WHERE watch_id=?", (watch_id,)
            ).fetchone()
            conn.execute("COMMIT")
            return _row(created)
        except Exception:
            conn.execute("ROLLBACK")
            raise


def get_watch(watch_id: str) -> dict | None:
    with _lock, _connect() as conn:
        return _row(conn.execute(
            "SELECT * FROM watches WHERE watch_id=?", (watch_id,)
        ).fetchone())


_ALLOWED_UPDATES = {
    "source_url", "scope", "last_checked_at", "last_result_state",
    "last_best_match_url", "active", "installation_id", "intent",
}


def update_watch(watch_id: str, **changes) -> dict | None:
    clean = {k: v for k, v in changes.items() if k in _ALLOWED_UPDATES}
    if "source_url" in clean and clean["source_url"]:
        clean["source_url"] = canonical_url(str(clean["source_url"]))
    if "active" in clean:
        clean["active"] = 1 if clean["active"] else 0
    if not clean:
        return get_watch(watch_id)

    columns = ", ".join(f"{k}=?" for k in clean)
    values = list(clean.values()) + [watch_id]
    with _lock, _connect() as conn:
        try:
            conn.execute(f"UPDATE watches SET {columns} WHERE watch_id=?", values)
        except sqlite3.IntegrityError:
            # Reactivating a duplicate should not create two active rows.
            return get_watch(watch_id)
        return _row(conn.execute(
            "SELECT * FROM watches WHERE watch_id=?", (watch_id,)
        ).fetchone())


def list_active() -> list[dict]:
    with _lock, _connect() as conn:
        rows = conn.execute("""
            SELECT * FROM watches
            WHERE active=1
            ORDER BY created_at ASC
        """).fetchall()
        return [_row(r) for r in rows]


def deactivate_watch(watch_id: str) -> dict | None:
    return update_watch(watch_id, active=False)


def _parse_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def list_due(*, interval_minutes: int = 360, limit: int = 10, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=max(60, interval_minutes))).isoformat()
    limit = max(1, min(limit, 50))
    with _lock, _connect() as conn:
        rows = conn.execute("""
            SELECT * FROM watches
            WHERE active=1
              AND (last_checked_at IS NULL OR last_checked_at <= ?)
            ORDER BY
              CASE WHEN last_checked_at IS NULL THEN 0 ELSE 1 END,
              last_checked_at ASC,
              created_at ASC
            LIMIT ?
        """, (cutoff, limit)).fetchall()
        return [_row(r) for r in rows]


def storage_info() -> dict:
    path = _path()
    with _lock, _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM watches").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM watches WHERE active=1").fetchone()[0]
    return {
        "backend": "sqlite",
        "path_configured": bool(os.getenv("FINDREST_WATCH_DB_PATH", "").strip() or os.getenv("FINDREST_WATCH_PATH", "").strip()),
        "total_watches": int(total),
        "active_watches": int(active),
    }
