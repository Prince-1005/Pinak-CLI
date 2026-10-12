from __future__ import annotations

import os
import re
import shutil
import sys
from typing import Any

# ANSI Color Codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

# Characters illegal on Windows/macOS/Linux filenames.
_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE_RUN = re.compile(r"\s+")


def sanitize_filename(name: str, max_length: int = 180) -> str:
    """Make a string safe to use as a file name on all major OSes."""
    cleaned = _ILLEGAL_FILENAME_CHARS.sub("_", (name or "untitled").strip())
    cleaned = _WHITESPACE_RUN.sub(" ", cleaned).strip()
    cleaned = cleaned.strip(" .")
    if not cleaned:
        cleaned = "untitled"
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(" .")
    return cleaned


def script_dir() -> str:
    """Returns the cli/ root directory where ffmpeg / ffprobe binaries may live.

    Search order (first directory containing a bundled binary wins):
      1. The directory of *this* file's package parent (cli/)
      2. The directory of *this* file (cli/pinak/) — edge case
      3. The current working directory
    Falls back gracefully to the cli/ directory guess.
    """
    pkg_dir = os.path.dirname(os.path.abspath(__file__))  # …/cli/pinak
    cli_dir = os.path.dirname(pkg_dir)  # …/cli
    candidates = (cli_dir, pkg_dir, os.getcwd())
    wanted = ("ffmpeg.exe", "ffmpeg", "ffprobe.exe", "ffprobe")
    for candidate in candidates:
        for binary in wanted:
            if os.path.exists(os.path.join(candidate, binary)):
                return candidate
    return cli_dir  # best guess even if binary not found there


def _resolve_binary(
    names: tuple[str, ...],
    config_override: str | None = None,
) -> str:
    """Resolve a binary path with the following precedence:

    1. Explicit config override (if the file exists).
    2. System PATH via ``shutil.which`` (cross-platform friendly).
    3. Bundled binary next to ``cli/`` (``ffmpeg.exe`` on Windows,
       ``ffmpeg`` on Linux/macOS).
    4. Bare command name as a last resort (lets subprocess raise a clear error).
    """
    if config_override:
        expanded = os.path.abspath(os.path.expanduser(config_override))
        if os.path.exists(expanded):
            return expanded
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    base = script_dir()
    for name in names:
        candidate = os.path.join(base, name)
        if os.path.exists(candidate):
            return candidate
    return names[0]


def _configured_binary_override(key: str) -> str | None:
    """Read an optional ffmpeg/ffprobe override from config without importing config at module load."""
    try:
        from .config import config as _config

        value = _config.get(key)
        if value:
            return str(value)
    except Exception:
        pass
    return None


def get_ffmpeg_path() -> str:
    """Return the best ffmpeg binary path.

    Precedence: config override → system PATH → bundled → "ffmpeg".
    Works on Windows (ffmpeg.exe), Linux and macOS (ffmpeg).
    """
    override = _configured_binary_override("ffmpeg_path")
    if sys.platform.startswith("win"):
        names: tuple[str, ...] = ("ffmpeg.exe", "ffmpeg")
    else:
        names = ("ffmpeg", "ffmpeg.exe")
    return _resolve_binary(names, config_override=override)


def get_ffprobe_path() -> str:
    """Return the best ffprobe binary path (same precedence as ffmpeg)."""
    override = _configured_binary_override("ffprobe_path")
    if sys.platform.startswith("win"):
        names = ("ffprobe.exe", "ffprobe")
    else:
        names = ("ffprobe", "ffprobe.exe")
    return _resolve_binary(names, config_override=override)


def ffmpeg_available() -> bool:
    """True if an ffmpeg binary can actually be executed."""
    path = get_ffmpeg_path()
    if os.path.exists(path):
        return True
    return shutil.which(os.path.basename(path)) is not None


def human_duration(seconds: Any) -> str:
    try:
        sec_int = int(float(str(seconds)))
    except (TypeError, ValueError):
        return "unknown"
    mins, secs = divmod(sec_int, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}h {mins}m {secs}s"
    if mins:
        return f"{mins}m {secs}s"
    return f"{secs}s"


def human_size(bytes_sz: object) -> str:
    try:
        bytes_sz = float(bytes_sz or 0)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "unknown"
    if bytes_sz == 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_sz < 1024.0:
            return f"{bytes_sz:.1f} {unit}"
        bytes_sz /= 1024.0
    return f"{bytes_sz:.1f} TB"


def get_all_files(folder: str) -> dict[str, float]:
    import contextlib

    files: dict[str, float] = {}
    for root, _, filenames in os.walk(folder):
        for f in filenames:
            full_path = os.path.join(root, f)
            with contextlib.suppress(OSError):
                files[full_path] = os.path.getmtime(full_path)
    return files


def get_file_snapshot(folder: str) -> dict[str, float]:
    if not os.path.exists(folder):
        return {}
    return get_all_files(folder)


def changed_files(before: dict[str, float], after: dict[str, float]) -> list[str]:
    files = []
    for path, state in after.items():
        if before.get(path) != state:
            files.append(path)
    return sorted(files)


def has_embedded_thumbnail(file_path: str) -> bool:
    from .subproc import run_cmd

    ffprobe = get_ffprobe_path()
    if not os.path.exists(ffprobe) or not os.path.exists(file_path):
        return False
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v",
        "-show_streams",
        "-of",
        "json",
        file_path,
    ]
    try:
        res = run_cmd(cmd, timeout=15.0)
        import json

        data = json.loads(res.stdout)
        if "streams" in data:
            for stream in data["streams"]:
                disposition = stream.get("disposition", {})
                if str(disposition.get("attached_pic", 0)) == "1":
                    return True
    except Exception:
        pass
    return False


def has_embedded_subtitle(file_path: str) -> bool:
    from .subproc import run_cmd

    ffprobe = get_ffprobe_path()
    if not os.path.exists(ffprobe) or not os.path.exists(file_path):
        return False
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "s",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "json",
        file_path,
    ]
    try:
        res = run_cmd(cmd, timeout=15.0)
        import json

        data = json.loads(res.stdout)
        if data.get("programs") or data.get("streams"):
            return True
    except Exception:
        pass
    return False


def is_online(timeout: float = 5.0) -> bool:
    """Check internet connectivity with a configurable timeout (seconds)."""
    import urllib.request

    try:
        connect_timeout = timeout
        try:
            from .config import config as _config

            connect_timeout = float(_config.get("connect_timeout", timeout))
        except Exception:
            pass

        # Try Google first, fall back to Cloudflare DNS endpoint
        for host in ("https://www.google.com", "https://1.1.1.1"):
            try:
                probe = urllib.request.Request(host, headers={"User-Agent": "PinakCLI"})
                # Fixed first-party HTTPS probe — no user-controlled scheme. nosec B310
                with urllib.request.urlopen(probe, timeout=connect_timeout):  # nosec B310
                    return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def get_platform(url: str) -> str:
    try:
        import yt_dlp

        extractors = yt_dlp.extractor.gen_extractors()
        for ie in extractors:
            if ie.suitable(url) and ie.IE_NAME != "generic":
                return ie.IE_NAME.split(":")[0].capitalize()
    except Exception:
        pass
    return "Unknown"


def normalize_quality(value: str | None) -> str | None:
    value = (value or "best").strip().lower()
    aliases = {"audio": "audio", "mp3": "audio", "best": "best", "worst": "worst"}
    if value in aliases:
        return aliases[value]
    match = re.fullmatch(r"(\d{3,4})p?", value)
    if match:
        return f"{match.group(1)}p"
    return None


def video_format_for_quality(quality: str | None) -> str:
    quality = normalize_quality(quality) or "best"
    if quality == "worst":
        return "worst"
    if quality.endswith("p"):
        height = quality[:-1]
        return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"
    return "bestvideo+bestaudio/best"
