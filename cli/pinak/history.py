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
import logging
import os
import sqlite3
import time
import uuid
from typing import Any

import platformdirs
from filelock import FileLock

from .utils import get_platform, human_duration, human_size

logger = logging.getLogger("pinak.history")

APP_NAME = "pinak-cli"
APP_AUTHOR = "pinak"

data_dir = os.path.abspath(
    os.environ.get("PINAK_DATA_DIR") or platformdirs.user_data_dir(APP_NAME, APP_AUTHOR)
)
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
# Remote tracking stubs (deprecated: intentionally retained as no-ops for backward compatibility)
# ---------------------------------------------------------------------------
def push_session_start() -> None:
    """[DEPRECATED] No-op stub: remote backend tracking has been removed."""


def push_session_end(wait: bool = True) -> None:
    """[DEPRECATED] No-op stub: remote backend tracking has been removed."""


def push_command_event(command: str, url: str | None = None, platform: str = "unknown") -> None:
    """[DEPRECATED] No-op stub: remote backend tracking has been removed."""


def push_download_event(*args: Any, **kwargs: Any) -> None:
    """[DEPRECATED] No-op stub: remote backend tracking has been removed."""


def _push_activity(payload: dict[str, Any], wait: bool = False) -> None:
    """[DEPRECATED] No-op stub: remote backend tracking has been removed."""


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
    parent = os.path.dirname(DB_FILE)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # Migrate legacy DB if it exists and new one doesn't
    if not os.path.exists(DB_FILE) and os.path.exists(LEGACY_DB_FILE):
        try:
            import shutil

            shutil.copy(LEGACY_DB_FILE, DB_FILE)
        except Exception as exc:
            logger.debug("Failed to copy legacy DB file: %s", exc)

    parent = os.path.dirname(DB_FILE)
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA schema_version")
        return conn
    except (sqlite3.DatabaseError, OSError) as exc:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()
        code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
        if code not in (11, 26) and str(exc).lower() not in (
            "file is not a database",
            "database disk image is malformed",
        ):
            raise
        # Only confirmed corruption permits quarantine. Recheck after obtaining
        # the cross-process recovery lock so another recovery is never replaced.
        with FileLock(DB_FILE + ".recovery.lock", timeout=5):
            with contextlib.closing(sqlite3.connect(DB_FILE, timeout=5.0)) as probe:
                try:
                    probe.execute("PRAGMA schema_version")
                except sqlite3.DatabaseError as current:
                    if (getattr(current, "sqlite_errorcode", 0) & 0xFF) not in (11, 26) and str(
                        current
                    ).lower() not in ("file is not a database", "database disk image is malformed"):
                        raise
                else:
                    conn = sqlite3.connect(DB_FILE, timeout=5.0)
                    conn.row_factory = sqlite3.Row
                    return conn
            corrupt_target = f"{DB_FILE}.corrupt.{uuid.uuid4().hex}"
            os.replace(DB_FILE, corrupt_target)
            logger.warning(
                "Corrupt history preserved at %s; starting a new database", corrupt_target
            )
            conn = sqlite3.connect(DB_FILE, timeout=5.0)
            conn.row_factory = sqlite3.Row
            _create_schema(conn)
            return conn


def init_db() -> None:
    conn = None
    try:
        conn = get_db_connection()
        _create_schema(conn)
        conn.close()
    except Exception as exc:
        logger.warning("Database initialization failed: %s", exc)
    finally:
        if conn is not None:
            conn.close()

    # Run migration if legacy JSON history exists
    local_paths = [
        LOCAL_HISTORY,
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), LOCAL_HISTORY),
    ]
    for p in local_paths:
        if os.path.exists(p):
            try:
                migrate_json_to_sqlite(p)
            except Exception as exc:
                logger.warning("Legacy history migration failed; original retained: %s", exc)
            break


def migrate_json_to_sqlite(json_path: str) -> None:
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return

    if not isinstance(data, dict) or not isinstance(data.get("downloads", []), list):
        logger.warning("Legacy history has an invalid schema; original retained: %s", json_path)
        return
    downloads = data.get("downloads", [])
    if any(not isinstance(item, (dict, int, float)) for item in downloads):
        logger.warning("Legacy history has invalid records; original retained: %s", json_path)
        return
    if any(
        isinstance(item, dict)
        and (
            not isinstance(item.get("files", []), list)
            or any(not isinstance(p, str) for p in item.get("files", []))
            or not isinstance(item.get("time", 0), (int, float))
        )
        for item in downloads
    ):
        logger.warning("Legacy history has invalid record values; original retained: %s", json_path)
        return
    if not downloads:
        with contextlib.suppress(OSError):
            os.rename(json_path, json_path + ".bak")
        return

    with contextlib.closing(get_db_connection()) as conn, conn:
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
    if not history_enabled():
        return
    conn = None
    try:
        conn = get_db_connection()
        insert_download(conn, url, status, mode, files or [], quality, duration, is_forced)
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("Failed to insert record into download history: %s", exc)
    finally:
        if conn is not None:
            conn.close()


def history_enabled() -> bool:
    try:
        from .config import config as _config

        return bool(_config.get("history_enabled", True))
    except Exception as exc:
        logger.debug("Failed to query history_enabled config: %s", exc)
        return True


def insert_download(
    conn: sqlite3.Connection,
    url: str,
    status: str,
    mode: str,
    files: list[str],
    quality: str | None,
    duration: int,
    is_forced: bool,
) -> None:
    """Insert into an existing transaction, allowing queue state and history to commit together."""
    total_size = 0
    for path in files:
        try:
            if os.path.isfile(path):
                total_size += os.path.getsize(path)
        except OSError:
            logger.warning("Could not measure downloaded file: %s", path)
    conn.execute(
        "INSERT INTO downloads (time, url, status, mode, quality, files, duration, size, is_forced) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            time.time(),
            url,
            status,
            mode,
            quality,
            json.dumps(files),
            int(duration),
            total_size,
            int(is_forced),
        ),
    )


def url_downloaded_successfully(url: str) -> bool:
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT files FROM downloads WHERE url = ? AND status = 'success'", (url,))
        records = cursor.fetchall()
        conn.close()
        for record in records:
            with contextlib.suppress(ValueError, TypeError, OSError):
                files = json.loads(record[0])
                if files and all(os.path.isfile(p) and os.path.getsize(p) > 0 for p in files):
                    return True
        return False
    except Exception:
        return False
    finally:
        if conn is not None:
            conn.close()


def get_history(filter_text: str = "") -> list[dict[str, Any]]:
    filter_text = (filter_text or "").strip().lower()

    conn = None
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
    except Exception as exc:
        logger.warning("History read failed: %s", exc)
        return []
    finally:
        if conn is not None:
            conn.close()

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


def clear_all_history() -> bool:
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM downloads")
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("Failed to clear download history: %s", exc)
        return False
    finally:
        if conn is not None:
            conn.close()


def delete_history_by_ids(ids_to_delete: list[int]) -> bool:
    if not ids_to_delete:
        return True
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Fully static SQL query using executemany — zero string interpolation or SQL injection risk.
        cursor.executemany("DELETE FROM downloads WHERE id = ?", [(i,) for i in ids_to_delete])
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("Failed to delete history records by IDs: %s", exc)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_history_ids_desc() -> list[int]:
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM downloads ORDER BY time DESC")
        rows = cursor.fetchall()
        conn.close()
        return [r["id"] for r in rows]
    except Exception as exc:
        logger.warning("History read failed: %s", exc)
        return []
    finally:
        if conn is not None:
            conn.close()


def get_stats_data() -> dict[str, Any] | None:
    conn = None
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
    except Exception as exc:
        logger.warning("History statistics unavailable: %s", exc)
        return None
    finally:
        if conn is not None:
            conn.close()

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
