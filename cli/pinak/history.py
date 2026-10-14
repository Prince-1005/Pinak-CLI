"""
pinak/history.py
================
Handles all local SQLite history storage.

Remote activity tracking was removed; the push_* functions below are
no-op stubs retained only for call-site backward compatibility.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import time
import uuid
from typing import Any

import platformdirs

from .utils import get_platform, human_duration, human_size

APP_NAME = "pinak-cli"
APP_AUTHOR = "pinak"

data_dir = platformdirs.user_data_dir(APP_NAME, APP_AUTHOR)
os.makedirs(data_dir, exist_ok=True)
DB_FILE = os.path.join(data_dir, "history.db")
LOCAL_HISTORY = ".pinak_history.json"
LEGACY_DB_FILE = os.path.expanduser("~/.pinak_history.db")


# ---------------------------------------------------------------------------
# In-memory session tracking
# ---------------------------------------------------------------------------
_session_id: str | None = None


def initialize_session() -> str:
    """Generate and store a new session ID. Call once at CLI startup."""
    global _session_id
    _session_id = str(uuid.uuid4())
    return _session_id


def get_current_session_id() -> str | None:
    """Return the active in-memory session ID, if initialized."""
    return _session_id


# ---------------------------------------------------------------------------
# Remote tracking stubs (intentionally retained as no-ops for backward compatibility)
# ---------------------------------------------------------------------------
def push_session_start() -> None:
    """No-op stub: remote backend tracking has been removed in this version."""


def push_session_end(wait: bool = True) -> None:
    """No-op stub: remote backend tracking has been removed in this version."""


def push_command_event(command: str, url: str | None = None, platform: str = "unknown") -> None:
    """No-op stub: remote backend tracking has been removed in this version."""


def push_download_event(*args: Any, **kwargs: Any) -> None:
    """No-op stub: remote backend tracking has been removed in this version."""


def _push_activity(payload: dict[str, Any], wait: bool = False) -> None:
    """No-op stub: remote backend tracking has been removed in this version."""


# ---------------------------------------------------------------------------
# Local SQLite helpers
# ---------------------------------------------------------------------------
def _create_schema(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS downloads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time REAL NOT NULL,
        url TEXT NOT NULL,
        status TEXT NOT NULL,
        mode TEXT,
        quality TEXT,
        files TEXT,
        duration INTEGER DEFAULT 0,
        size INTEGER DEFAULT 0,
        is_forced INTEGER DEFAULT 0
    )
    """)
    with contextlib.suppress(sqlite3.OperationalError):  # Column already exists
        cursor.execute("ALTER TABLE downloads ADD COLUMN is_forced INTEGER DEFAULT 0")
    conn.commit()


def get_db_connection() -> sqlite3.Connection:
    # Migrate legacy DB if it exists and new one doesn't
    if not os.path.exists(DB_FILE) and os.path.exists(LEGACY_DB_FILE):
        try:
            import shutil

            shutil.copy(LEGACY_DB_FILE, DB_FILE)
        except Exception:
            pass

    parent = os.path.dirname(DB_FILE)
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA schema_version")
        return conn
    except (sqlite3.DatabaseError, OSError):
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()
        # Self-healing: quarantine corrupt database and start clean
        with contextlib.suppress(Exception):
            corrupt_target = f"{DB_FILE}.corrupt.{int(time.time())}"
            if os.path.exists(DB_FILE):
                os.replace(DB_FILE, corrupt_target)

        conn = sqlite3.connect(DB_FILE, timeout=5.0)
        conn.row_factory = sqlite3.Row
        with contextlib.suppress(Exception):
            _create_schema(conn)
        return conn


def init_db() -> None:
    try:
        conn = get_db_connection()
        _create_schema(conn)
        conn.close()
    except Exception:
        pass

    # Run migration if legacy JSON history exists
    local_paths = [
        LOCAL_HISTORY,
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), LOCAL_HISTORY),
    ]
    for p in local_paths:
        if os.path.exists(p):
            migrate_json_to_sqlite(p)
            break


def migrate_json_to_sqlite(json_path: str) -> None:
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return

    downloads = data.get("downloads", [])
    if not downloads:
        with contextlib.suppress(OSError):
            os.rename(json_path, json_path + ".bak")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    for item in downloads:
        if isinstance(item, dict):
            t_val = item.get("time", time.time())
            url = item.get("url", "Unknown URL")
            status = item.get("status", "success")
            mode = item.get("mode", "media")
            quality = item.get("quality", "best")
            files = item.get("files", [])

            total_size = 0
            for f in files:
                if os.path.exists(f):
                    total_size += os.path.getsize(f)

            files_str = json.dumps(files)
            cursor.execute(
                """
            INSERT INTO downloads (time, url, status, mode, quality, files, duration, size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (t_val, url, status, mode, quality, files_str, 0, total_size),
            )
        else:
            cursor.execute(
                """
            INSERT INTO downloads (time, url, status, mode, quality, files, duration, size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (float(item), "Legacy Entry", "success", "media", "best", "[]", 0, 0),
            )

    conn.commit()
    conn.close()

    try:
        os.rename(json_path, json_path + ".bak")
    except OSError:
        with contextlib.suppress(OSError):
            os.remove(json_path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def record_download(
    url: str,
    status: str = "success",
    mode: str = "media",
    files: list[str] | None = None,
    quality: str | None = None,
    duration: int = 0,
    is_forced: bool = False,
) -> None:
    files = files or []
    try:
        from .config import config as _config

        if not _config.get("history_enabled", True):
            return
    except Exception:
        pass

    # Calculate file sizes
    total_size = 0
    for f in files:
        if os.path.exists(f):
            total_size += os.path.getsize(f)

    files_str = json.dumps(files)
    current_time = time.time()

    # --- Save to local SQLite ---
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
        INSERT INTO downloads (time, url, status, mode, quality, files, duration, size, is_forced)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                current_time,
                url,
                status,
                mode,
                quality,
                files_str,
                int(duration),
                total_size,
                int(is_forced),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def url_downloaded_successfully(url: str) -> bool:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM downloads WHERE url = ? AND status = 'success'", (url,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def get_history(filter_text: str = "") -> list[dict[str, Any]]:
    filter_text = (filter_text or "").strip().lower()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if filter_text in ("failed", "success"):
            cursor.execute(
                "SELECT * FROM downloads WHERE LOWER(status) = ? ORDER BY time ASC",
                (filter_text,),
            )
        elif filter_text in ("audio", "media"):
            cursor.execute(
                "SELECT * FROM downloads WHERE LOWER(mode) = ? ORDER BY time ASC",
                (filter_text,),
            )
        elif filter_text.startswith("search "):
            term = "%" + filter_text[7:].strip() + "%"
            cursor.execute(
                "SELECT * FROM downloads WHERE url LIKE ? OR files LIKE ? ORDER BY time ASC",
                (term, term),
            )
        else:
            cursor.execute("SELECT * FROM downloads ORDER BY time ASC")

        rows = cursor.fetchall()
        conn.close()
    except Exception:
        return []

    results = []
    for r in rows:
        try:
            files = json.loads(r["files"]) if r["files"] else []
        except (json.JSONDecodeError, TypeError):
            files = []
        row_keys = r.keys()
        results.append(
            {
                "time": r["time"],
                "url": r["url"],
                "status": r["status"],
                "mode": r["mode"],
                "quality": r["quality"],
                "files": files,
                "duration": r["duration"],
                "size": r["size"],
                "is_forced": bool(r["is_forced"]) if "is_forced" in row_keys else False,
            }
        )
    return results


def clear_all_history() -> None:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM downloads")
        conn.commit()
        conn.close()
    except Exception:
        pass


def delete_history_by_ids(ids_to_delete: list[int]) -> None:
    if not ids_to_delete:
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Fully static SQL query using executemany — zero string interpolation or SQL injection risk.
        cursor.executemany("DELETE FROM downloads WHERE id = ?", [(i,) for i in ids_to_delete])
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_history_ids_desc() -> list[int]:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM downloads ORDER BY time DESC")
        rows = cursor.fetchall()
        conn.close()
        return [r["id"] for r in rows]
    except Exception:
        return []


def get_stats_data() -> dict[str, Any] | None:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM downloads")
        total_attempts = cursor.fetchone()[0]

        if total_attempts == 0:
            conn.close()
            return None

        cursor.execute("SELECT COUNT(*) FROM downloads WHERE status = 'success'")
        successes = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(size) FROM downloads WHERE status = 'success'")
        total_size_bytes = cursor.fetchone()[0] or 0

        cursor.execute("SELECT SUM(duration) FROM downloads WHERE status = 'success'")
        total_duration_sec = cursor.fetchone()[0] or 0

        cursor.execute("SELECT url FROM downloads WHERE status = 'success'")
        urls = [r["url"] for r in cursor.fetchall()]
        conn.close()
    except Exception:
        return None

    platform_counts: dict[str, int] = {}
    for url in urls:
        platform = get_platform(url)
        if platform != "Unknown":
            platform_counts[platform] = platform_counts.get(platform, 0) + 1

    if platform_counts:
        top_platform, top_count = max(platform_counts.items(), key=lambda kv: kv[1])
    else:
        top_platform, top_count = "None", 0

    success_rate = (successes / total_attempts) * 100 if total_attempts > 0 else 0
    buffer_saved_sec = int(total_duration_sec * 1.5)

    return {
        "total_attempts": total_attempts,
        "successes": successes,
        "success_rate": success_rate,
        "total_size_str": human_size(total_size_bytes),
        "total_duration_str": human_duration(total_duration_sec),
        "buffer_saved_str": human_duration(buffer_saved_sec),
        "top_platform": (f"{top_platform} ({top_count} downloads)" if top_count > 0 else "N/A"),
    }
