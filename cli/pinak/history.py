"""
pinak/history.py
=================
Handles all local SQLite history storage AND remote activity tracking.

Remote tracking architecture:
  CLI  →  POST /api/v1/track  →  Render backend  →  Supabase
  (credentials NEVER leave the backend; CLI only knows the public backend URL)

The backend URL is embedded here as a constant. It is NOT secret.
All sensitive credentials are stored server-side on Render only.
"""

import os
import sqlite3
import json
import time
import uuid
import hashlib
import platform
import threading
from .utils import get_platform, human_size, human_duration

import platformdirs

APP_NAME = "pinak-cli"
APP_AUTHOR = "pinak"

data_dir = platformdirs.user_data_dir(APP_NAME, APP_AUTHOR)
os.makedirs(data_dir, exist_ok=True)
DB_FILE = os.path.join(data_dir, "history.db")
LOCAL_HISTORY = ".pinak_history.json"
LEGACY_DB_FILE = os.path.expanduser("~/.pinak_history.db")
DEVICE_ID_FILE = os.path.join(data_dir, "device.id")

# ---------------------------------------------------------------------------
# Backend server configuration
# ---------------------------------------------------------------------------
BACKEND_URL: str = os.environ.get(
    "PINAK_PROXY_URL",
    "https://pinak-cli-backend.onrender.com"  # Render backend URL
)
BACKEND_TOKEN: str = os.environ.get(
    "PINAK_API_TOKEN",
    ""  # set PINAK_API_TOKEN env var (used as HMAC secret)
)
PROXY_TIMEOUT: int = 5  # seconds — never blocks the user longer than this

# ---------------------------------------------------------------------------
# Persistent Device ID — survives reinstalls; based on hardware fingerprint
# ---------------------------------------------------------------------------
def _generate_hardware_fingerprint() -> str:
    """
    Build a stable fingerprint from hardware identifiers so the device_id
    survives uninstalls and reinstalls. Falls back to a random UUID stored
    on disk if hardware info is unavailable.
    """
    parts = []
    try:
        # Machine node (MAC address) is stable across reinstalls
        parts.append(str(uuid.getnode()))
    except Exception:
        pass
    try:
        parts.append(platform.node())  # hostname
    except Exception:
        pass
    try:
        parts.append(platform.machine())  # e.g. AMD64
    except Exception:
        pass
    try:
        parts.append(platform.processor())  # CPU string
    except Exception:
        pass

    if parts:
        raw = "-".join(parts).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:32]
    return ""


def get_device_id() -> str:
    """
    Return a stable device ID. Reads from disk first; if absent, generates
    from hardware fingerprint (or random UUID as last resort) and persists it.
    """
    if os.path.exists(DEVICE_ID_FILE):
        try:
            with open(DEVICE_ID_FILE, "r", encoding="utf-8") as f:
                did = f.read().strip()
                if did:
                    return did
        except Exception:
            pass

    # Not on disk – generate now
    did = _generate_hardware_fingerprint()
    if not did:
        did = uuid.uuid4().hex  # last resort

    try:
        with open(DEVICE_ID_FILE, "w", encoding="utf-8") as f:
            f.write(did)
    except Exception:
        pass
    return did


# ---------------------------------------------------------------------------
# In-memory session tracking
# ---------------------------------------------------------------------------
_session_id: str | None = None
_session_start_time: float | None = None


def initialize_session() -> str:
    """Generate and store a new session ID. Call once at CLI startup."""
    global _session_id, _session_start_time
    _session_id = str(uuid.uuid4())
    _session_start_time = time.time()
    return _session_id


# ---------------------------------------------------------------------------
# HTTP backend helper — fire-and-forget in a daemon thread
# ---------------------------------------------------------------------------
def _push_to_backend(payload: dict, wait: bool = False) -> None:
    """
    Send a tracking payload to the backend server in a background thread.
    - Never raises.
    - If wait=True, blocks for up to PROXY_TIMEOUT seconds (useful at exit).
    - Silently drops the event if the server is unreachable.
    """
    def _send():
        try:
            import urllib.request
            import hmac as hmac_module
            import hashlib
            body = json.dumps(payload).encode("utf-8")

            headers = {
                "Content-Type": "application/json",
                "User-Agent": "pinak-cli/1.0",
            }

            if BACKEND_TOKEN:
                timestamp = str(int(time.time()))
                secret = BACKEND_TOKEN.encode("utf-8")
                sig = hmac_module.new(
                    secret,
                    f"{timestamp}.{json.dumps(payload)}".encode("utf-8"),
                    hashlib.sha256  # fix: must be a callable, not a string
                ).hexdigest()
                headers["x-pinak-timestamp"] = timestamp
                headers["x-pinak-signature"] = sig

            req = urllib.request.Request(
                f"{BACKEND_URL.rstrip('/')}/api/v1/track",
                data=body,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=PROXY_TIMEOUT):
                pass  # success
        except Exception:
            pass  # fail-soft

    t = threading.Thread(target=_send, daemon=True)
    t.start()
    if wait:
        t.join(timeout=PROXY_TIMEOUT)


def _build_base_payload(activity_type: str, command: str = "pinak") -> dict:
    """Build the standard payload base, shared by all activity events."""
    try:
        from .config import config
        username = config.get("username", "anonymous").strip() or "anonymous"
    except Exception:
        username = "anonymous"

    return {
        "activity_type": activity_type,
        "username": username,
        "device_id": get_device_id(),
        "session_id": _session_id or "",
        "command": command,
        "url": None,
        "status": None,
        "platform": "unknown",
        "mode": None,
        "duration": 0,
        "size": 0,
    }


def push_session_start() -> None:
    """Push a session_start event when the CLI starts."""
    payload = _build_base_payload("session_start", command="pinak")
    _push_to_backend(payload)


def push_session_end(wait: bool = True) -> None:
    """Push a session_end event when the CLI exits. Blocks briefly to ensure delivery."""
    payload = _build_base_payload("session_end", command="pinak")
    _push_to_backend(payload, wait=wait)


def push_command_event(command: str, url: str = None, platform: str = "unknown") -> None:
    """Push a generic command event (non-download commands)."""
    payload = _build_base_payload("command", command=command)
    payload["url"] = url
    payload["platform"] = platform
    _push_to_backend(payload)


def push_download_event(
    url: str,
    command: str,
    status: str,
    mode: str = "video",
    duration: int = 0,
    size: int = 0,
    platform: str = "unknown",
) -> None:
    """Push a download activity event."""
    payload = _build_base_payload("download", command=command)
    payload["url"] = url
    payload["status"] = status
    payload["mode"] = mode
    payload["duration"] = int(duration)
    payload["size"] = int(size)
    payload["platform"] = platform
    _push_to_backend(payload)


# ---------------------------------------------------------------------------
# Backward-compatible wrapper used by record_download()
# ---------------------------------------------------------------------------
def _push_activity(payload: dict, wait: bool = False) -> None:
    """
    Maps the record_download() payload into a clean push_download_event() call.
    Command format:
      /video [quality] [format]   e.g. /video 720p mp4
      /audio [quality] [format]   e.g. /audio 192k mp3
      /trim  [quality] [format]   e.g. /trim 480p mp4
    """
    url = payload.get("url", "")
    mode = payload.get("mode", "video") or "video"
    status = payload.get("status", "success")
    duration = int(payload.get("duration", 0) or 0)
    size = int(payload.get("size", 0) or 0)
    plat = payload.get("platform") or get_platform(url)

    # Pick base command from mode
    if mode == "audio":
        cmd_parts = ["/audio"]
    elif mode == "trim":
        cmd_parts = ["/trim"]
    else:
        cmd_parts = ["/video"]

    # Append quality (skip generic values)
    quality = (payload.get("quality") or "").strip()
    if quality and quality.lower() not in ("", "unknown", "best", "worst"):
        cmd_parts.append(quality)

    # Append file extension/format from downloaded files list
    files = payload.get("files") or []
    if files:
        _, ext = os.path.splitext(str(files[0]))
        ext = ext.lstrip(".").lower()
        if ext:
            cmd_parts.append(ext)

    push_download_event(
        url=url,
        command=" ".join(cmd_parts),
        status=status.upper() if status else "SUCCESS",
        mode=mode,
        duration=duration,
        size=size,
        platform=plat,
    )


# ---------------------------------------------------------------------------
# Local SQLite helpers
# ---------------------------------------------------------------------------
def get_db_connection():
    # Migrate legacy DB if it exists and new one doesn't
    if not os.path.exists(DB_FILE) and os.path.exists(LEGACY_DB_FILE):
        try:
            import shutil
            shutil.copy(LEGACY_DB_FILE, DB_FILE)
        except Exception:
            pass

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
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
    try:
        cursor.execute("ALTER TABLE downloads ADD COLUMN is_forced INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.commit()
    conn.close()

    # Run migration if legacy JSON history exists
    local_paths = [
        LOCAL_HISTORY,
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), LOCAL_HISTORY),
    ]
    for p in local_paths:
        if os.path.exists(p):
            migrate_json_to_sqlite(p)
            break


def migrate_json_to_sqlite(json_path):
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return

    downloads = data.get("downloads", [])
    if not downloads:
        try:
            os.rename(json_path, json_path + ".bak")
        except OSError:
            pass
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
            cursor.execute("""
            INSERT INTO downloads (time, url, status, mode, quality, files, duration, size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (t_val, url, status, mode, quality, files_str, 0, total_size))
        else:
            cursor.execute("""
            INSERT INTO downloads (time, url, status, mode, quality, files, duration, size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (float(item), "Legacy Entry", "success", "media", "best", "[]", 0, 0))

    conn.commit()
    conn.close()

    try:
        os.rename(json_path, json_path + ".bak")
    except OSError:
        try:
            os.remove(json_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def record_download(url, status="success", mode="media", files=None, quality=None, duration=0, is_forced=False):
    files = files or []

    # Calculate file sizes
    total_size = 0
    for f in files:
        if os.path.exists(f):
            total_size += os.path.getsize(f)

    files_str = json.dumps(files)
    current_time = time.time()

    if status == "success":
        from .config import config
        rate_limit_hours = int(config.get("rate_limit_hours", 1))
        window_file = os.path.join(data_dir, "window_start.txt")
        window_start = 0.0
        if os.path.exists(window_file):
            try:
                with open(window_file, 'r') as f:
                    window_start = float(f.read().strip())
            except: pass
        if current_time > window_start + (rate_limit_hours * 3600):
            with open(window_file, 'w') as f:
                f.write(str(current_time))

    # --- Save to local SQLite ---
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO downloads (time, url, status, mode, quality, files, duration, size, is_forced)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (current_time, url, status, mode, quality, files_str, int(duration), total_size, int(is_forced)))
    conn.commit()
    conn.close()

    # --- Push to remote backend (fire-and-forget, non-blocking) ---
    _push_activity({
        "activity_type": "download",
        "url": url,
        "status": status,
        "mode": mode,
        "quality": quality or "unknown",
        "files": files,           # pass actual file list so format can be extracted
        "duration": int(duration),
        "size": total_size,
        "session_id": _session_id or "",
        "platform": get_platform(url),
    })


def get_rate_limit_info(rate_limit_hours=1, normal_limit=5, force_limit=5):
    window_file = os.path.join(data_dir, "window_start.txt")
    current_time = time.time()
    
    window_start = 0.0
    if os.path.exists(window_file):
        try:
            with open(window_file, 'r') as f:
                window_start = float(f.read().strip())
        except: pass
        
    reset_time = window_start + (rate_limit_hours * 3600)
    if current_time > reset_time:
        return {
            "active": False,
            "normal_remaining": normal_limit,
            "force_remaining": force_limit,
            "reset_time_str": "Not started",
            "reset_seconds": 0
        }
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM downloads WHERE time >= ? AND status = 'success' AND is_forced = 0", (window_start,))
    normal_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM downloads WHERE time >= ? AND status = 'success' AND is_forced = 1", (window_start,))
    force_count = cursor.fetchone()[0]
    conn.close()
    
    remaining_secs = max(0, int(reset_time - current_time))
    mins, secs = divmod(remaining_secs, 60)
    
    return {
        "active": True,
        "normal_remaining": max(0, normal_limit - normal_count),
        "force_remaining": max(0, force_limit - force_count),
        "reset_time_str": f"{mins}m {secs}s",
        "reset_seconds": remaining_secs
    }

def check_rate_limit(rate_limit_hours=12, limit_count=5, check_forced=False):
    from .config import config
    normal_limit = int(config.get("rate_limit_count", 5))
    force_limit = int(config.get("force_rate_limit_count", 5))
    
    info = get_rate_limit_info(rate_limit_hours, normal_limit, force_limit)
    if not info["active"]:
        return True
        
    if check_forced:
        return info["force_remaining"] > 0
    else:
        return info["normal_remaining"] > 0


def url_downloaded_successfully(url):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM downloads WHERE url = ? AND status = 'success'", (url,))
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0


def get_history(filter_text=""):
    conn = get_db_connection()
    cursor = conn.cursor()

    filter_text = (filter_text or "").strip().lower()

    if filter_text in ("failed", "success"):
        cursor.execute("SELECT * FROM downloads WHERE LOWER(status) = ? ORDER BY time ASC", (filter_text,))
    elif filter_text in ("audio", "media"):
        cursor.execute("SELECT * FROM downloads WHERE LOWER(mode) = ? ORDER BY time ASC", (filter_text,))
    elif filter_text.startswith("search "):
        term = "%" + filter_text[7:].strip() + "%"
        cursor.execute("SELECT * FROM downloads WHERE url LIKE ? OR files LIKE ? ORDER BY time ASC", (term, term))
    else:
        cursor.execute("SELECT * FROM downloads ORDER BY time ASC")

    rows = cursor.fetchall()
    conn.close()

    results = []
    for r in rows:
        try:
            files = json.loads(r["files"]) if r["files"] else []
        except (json.JSONDecodeError, TypeError):
            files = []
        results.append({
            "time": r["time"],
            "url": r["url"],
            "status": r["status"],
            "mode": r["mode"],
            "quality": r["quality"],
            "files": files,
            "duration": r["duration"],
            "size": r["size"],
        })
    return results


def clear_all_history():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM downloads")
    conn.commit()
    conn.close()

def delete_history_by_ids(ids_to_delete):
    if not ids_to_delete:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in ids_to_delete)
    cursor.execute(f"DELETE FROM downloads WHERE id IN ({placeholders})", ids_to_delete)
    conn.commit()
    conn.close()

def get_history_ids_desc():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM downloads ORDER BY time DESC")
    rows = cursor.fetchall()
    conn.close()
    return [r["id"] for r in rows]


def get_stats_data():
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
        "top_platform": f"{top_platform} ({top_count} downloads)" if top_count > 0 else "N/A",
    }
