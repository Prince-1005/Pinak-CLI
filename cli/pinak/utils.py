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


def trusted_which(name: str) -> str | None:
    """Resolve only absolute PATH entries, never Windows' implicit current directory."""
    cwd = os.path.normcase(os.path.realpath(os.getcwd()))
    for directory in os.get_exec_path():
        if not directory or not os.path.isabs(directory):
            continue
        if os.path.normcase(os.path.realpath(directory)) == cwd:
            continue
        found = shutil.which(os.path.join(directory, name))
        if found and os.path.isfile(found) and os.access(found, os.X_OK):
            return found
    return None


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
    Falls back gracefully to the cli/ directory guess.
    """
    pkg_dir = os.path.dirname(os.path.abspath(__file__))  # …/cli/pinak
    cli_dir = os.path.dirname(pkg_dir)  # …/cli
    candidates = (cli_dir, pkg_dir)
    wanted = ("ffmpeg.exe", "ffmpeg", "ffprobe.exe", "ffprobe")
    for candidate in candidates:
        for binary in wanted:
            if os.path.isfile(os.path.join(candidate, binary)):
                return candidate
    return cli_dir  # best guess even if binary not found there


def _get_platform_candidate_dirs() -> list[str]:
    """Return well-known fallback directories for package managers and environments."""
    dirs: list[str] = []
    if sys.platform.startswith("win"):
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            dirs.append(os.path.join(local_app, "Microsoft", "WinGet", "Links"))
        user_prof = os.environ.get("USERPROFILE", "")
        if user_prof:
            dirs.append(os.path.join(user_prof, "scoop", "shims"))
            dirs.append(os.path.join(user_prof, "scoop", "apps", "ffmpeg", "current", "bin"))
        dirs.append(r"C:\ProgramData\chocolatey\bin")
        dirs.append(r"C:\ffmpeg\bin")
    else:
        dirs.extend(
            [
                "/data/data/com.termux/files/usr/bin",  # Android Termux
                "/usr/local/bin",
                "/opt/homebrew/bin",  # macOS Apple Silicon Homebrew
                "/opt/local/bin",  # macOS MacPorts
                "/usr/bin",
                "/snap/bin",
            ]
        )
    return [d for d in dirs if os.path.isdir(d)]


_static_ffmpeg_initialized = False


def _ensure_static_ffmpeg_paths() -> None:
    """Ensure static-ffmpeg binaries are prepended to PATH if installed."""
    global _static_ffmpeg_initialized
    if not _static_ffmpeg_initialized:
        _static_ffmpeg_initialized = True
        try:
            import static_ffmpeg  # type: ignore

            static_ffmpeg.add_paths()
        except Exception:
            pass


def _resolve_binary(
    names: tuple[str, ...],
    config_override: str | None = None,
    *,
    allow_provision: bool = True,
) -> str:
    """Resolve a binary path with the following precedence:

    1. Explicit config override (if the file exists).
    2. System PATH via ``shutil.which`` (cross-platform friendly).
    3. Bundled binary next to ``cli/`` (``ffmpeg.exe`` on Windows,
       ``ffmpeg`` on Linux/macOS).
    4. Well-known package manager / environment locations (Winget, Scoop, Choco, Termux, Homebrew).
    5. static-ffmpeg package (if installed in the python environment).
    6. Bare command name as a last resort (lets subprocess raise a clear error).
    """
    if config_override:
        expanded = os.path.abspath(os.path.expanduser(config_override))
        if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
            return expanded
    for name in names:
        found = trusted_which(name)
        if found:
            return found
    base = script_dir()
    for name in names:
        candidate = os.path.join(base, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    for d in _get_platform_candidate_dirs():
        for name in names:
            candidate = os.path.join(d, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    # Try static-ffmpeg if installed
    if allow_provision:
        _ensure_static_ffmpeg_paths()
        for name in names:
            found = trusted_which(name)
            if found:
                return found
    # An unresolved bare executable could still be implicitly executed from CWD
    # by Windows or an external dependency. Return a controlled missing path.
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "_unavailable", names[0])


def _configured_binary_override(key: str) -> str | None:
    """Read an optional ffmpeg/ffprobe override from config without importing config at module load."""
    try:
        from .engine import active_setting

        value = active_setting(key)
        if value:
            return str(value)
    except Exception:
        pass
    return None


def get_ffmpeg_path(*, allow_provision: bool = True) -> str:
    """Return the best ffmpeg binary path.

    Precedence: config override → system PATH → bundled → "ffmpeg".
    Works on Windows (ffmpeg.exe), Linux and macOS (ffmpeg).
    """
    override = _configured_binary_override("ffmpeg_path")
    if sys.platform.startswith("win"):
        names: tuple[str, ...] = ("ffmpeg.exe", "ffmpeg")
    else:
        names = ("ffmpeg", "ffmpeg.exe")
    return _resolve_binary(names, config_override=override, allow_provision=allow_provision)


def get_ffprobe_path(*, allow_provision: bool = True) -> str:
    """Return the best ffprobe binary path (same precedence as ffmpeg)."""
    override = _configured_binary_override("ffprobe_path")
    if sys.platform.startswith("win"):
        names = ("ffprobe.exe", "ffprobe")
    else:
        names = ("ffprobe", "ffprobe.exe")
    return _resolve_binary(names, config_override=override, allow_provision=allow_provision)


def ffmpeg_available() -> bool:
    """True if an ffmpeg binary can actually be executed."""
    path = get_ffmpeg_path()
    return os.path.isfile(path) and os.access(path, os.X_OK)


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


def get_all_files(folder: str) -> dict[str, tuple[float, int]]:
    import contextlib

    files: dict[str, tuple[float, int]] = {}
    for root, _, filenames in os.walk(folder):
        for f in filenames:
            full_path = os.path.join(root, f)
            with contextlib.suppress(OSError):
                st = os.stat(full_path)
                files[full_path] = (st.st_mtime, st.st_size)
    return files


def get_file_snapshot(folder: str) -> dict[str, Any]:
    if not os.path.exists(folder):
        return {}
    return get_all_files(folder)


def changed_files(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    files = []
    for path, state in after.items():
        before_state = before.get(path)
        if before_state is None:
            files.append(path)
        elif before_state != state:
            if isinstance(before_state, (int, float)) and isinstance(state, tuple):
                if before_state != state[0]:
                    files.append(path)
            else:
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
    """Check internet connectivity with a configurable timeout (seconds).

    Uses a tiered fallback approach:
      1. Major HTTPS endpoints (Google, Cloudflare direct IP, Cloudflare web, Httpbin).
      2. Low-level TCP socket connection to known reliable DNS IPs (1.1.1.1, 8.8.8.8 on port 53).
    """
    import socket
    import urllib.request

    try:
        connect_timeout = timeout
        try:
            from .engine import active_setting

            connect_timeout = float(active_setting("connect_timeout", timeout))
        except Exception:
            pass

        # Tier 1: HTTPS probes across multiple independent CDNs/hosts
        hosts = (
            "https://www.google.com",
            "https://1.1.1.1",
            "https://www.cloudflare.com",
            "https://httpbin.org/status/200",
        )
        for host in hosts:
            try:
                probe = urllib.request.Request(host, headers={"User-Agent": "PinakCLI"})
                # Fixed first-party HTTPS probe — no user-controlled scheme. nosec B310
                with urllib.request.urlopen(probe, timeout=connect_timeout):  # nosec B310
                    return True
            except Exception:
                continue

        # Tier 2: Low-level socket fallback (bypasses HTTP proxy, TLS, or DNS issues)
        sock_timeout = min(connect_timeout, 2.0)
        for ip, port in (("1.1.1.1", 53), ("8.8.8.8", 53)):
            try:
                with socket.create_connection((ip, port), timeout=sock_timeout):
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


def is_url_supported_by_ytdlp(url: str) -> tuple[bool, str]:
    """Check if a URL is an allowed/supported link type by yt-dlp.

    Returns ``(is_supported, platform_or_reason)``.
    Supports:
      1. Any platform with a dedicated yt-dlp extractor (YouTube, TikTok, Twitter/X, Instagram,
         Facebook, Reddit, Vimeo, SoundCloud, Twitch, Bilibili, and 1700+ others).
      2. Direct media URLs (.mp4, .mp3, .m3u8, .mpd, .webm, .mkv, etc.) handled by yt-dlp.
    Rejects:
      - Non-HTTP/HTTPS URLs (ftp, file, mailto, invalid text).
      - Generic websites with no supported media/extractor (e.g. google.com, github.com).
    """
    if not url or not isinstance(url, str) or not url.strip():
        return False, "Empty URL"

    clean_url = url.strip()
    if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
        return False, "Not an allowed link type: URL must start with http:// or https://"

    platform = get_platform(clean_url)
    if platform != "Unknown":
        return True, platform

    import urllib.parse

    parsed = urllib.parse.urlparse(clean_url)
    path = parsed.path.lower()
    media_exts = (
        ".mp4",
        ".m4a",
        ".m4v",
        ".mp3",
        ".mkv",
        ".webm",
        ".flv",
        ".avi",
        ".mov",
        ".wav",
        ".aac",
        ".flac",
        ".opus",
        ".ogg",
        ".ogv",
        ".m3u8",
        ".mpd",
        ".ts",
    )
    if any(path.endswith(ext) for ext in media_exts):
        return True, "Direct Media"

    try:
        import yt_dlp

        class _QuietProbeLogger:
            def debug(self, msg: str) -> None:
                pass

            def info(self, msg: str) -> None:
                pass

            def warning(self, msg: str) -> None:
                pass

            def error(self, msg: str) -> None:
                pass

        ydl = yt_dlp.YoutubeDL(
            {
                "logger": _QuietProbeLogger(),
                "simulate": True,
                "skip_download": True,
                "socket_timeout": 5,
            }
        )
        info = ydl.extract_info(clean_url, download=False)
        if info:
            domain = parsed.netloc.split(":")[0]
            if domain.startswith("www."):
                domain = domain[4:]
            return True, domain.capitalize() if domain else "Web Media"
    except Exception:
        pass

    return False, f"Not an allowed link type: '{clean_url}' is not supported by yt-dlp."


def normalize_quality(value: str | None) -> str | None:
    value = (value or "best").strip().lower()
    aliases = {"audio": "audio", "mp3": "audio", "best": "best", "worst": "worst"}
    if value in aliases:
        return aliases[value]
    match = re.fullmatch(r"(\d{3,4})p?", value)
    if match:
        return f"{match.group(1)}p"
    return None


def video_format_for_quality(quality: str | None, has_ffmpeg: bool = True) -> str:
    quality = normalize_quality(quality) or "best"
    if quality == "worst":
        return "worst"
    if not has_ffmpeg:
        if quality.endswith("p"):
            height = quality[:-1]
            return f"best[height<={height}][ext=mp4]/best[height<={height}]/best"
        return "best[ext=mp4]/best"
    if quality.endswith("p"):
        height = quality[:-1]
        return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"
    return "bestvideo+bestaudio/best"
