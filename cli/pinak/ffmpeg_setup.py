"""FFmpeg provisioning fallback.

Resolution order for an *executable* ffmpeg binary:

1. :func:`pinak.utils.get_ffmpeg_path` (config override → PATH → bundled).
2. The ``static-ffmpeg`` PyPI package (optional ``pinak-cli[ffmpeg]`` extra),
   which downloads a static build into the user cache on first use.
3. Bare ``"ffmpeg"`` name (lets the caller emit an actionable error).

Everything is best-effort and never raises: callers fall back to clear
user-facing hints when no binary can be provided.
"""

from __future__ import annotations

import os
import shutil
import sys

from .logging_setup import get_logger
from .utils import get_ffmpeg_path, get_ffprobe_path

log = get_logger("pinak.ffmpeg")


def _is_executable(path: str) -> bool:
    if not path:
        return False
    if os.path.exists(path):
        return os.access(path, os.X_OK) or path.lower().endswith(".exe")
    return shutil.which(path) is not None or shutil.which(os.path.basename(path)) is not None


_last_static_ffmpeg_id: int | None = None


def _try_static_ffmpeg() -> bool:
    """Fetch static builds via the optional ``static-ffmpeg`` package.

    Returns True if an ffmpeg binary became available afterwards.
    """
    global _last_static_ffmpeg_id
    try:
        import static_ffmpeg  # type: ignore
    except ImportError:
        log.debug("static-ffmpeg not installed; skipping auto-fetch")
        return False
    current_id = id(static_ffmpeg)
    if _last_static_ffmpeg_id != current_id:
        try:
            # Downloads version-pinned static builds into the user cache on
            # first call, then prepends them to PATH for this process.
            static_ffmpeg.add_paths()  # type: ignore[attr-defined]
            _last_static_ffmpeg_id = current_id
        except Exception as exc:
            log.debug("static-ffmpeg fetch failed: %r", exc)
            return False
    available = _is_executable(shutil.which("ffmpeg") or "") or _is_executable(get_ffmpeg_path())
    log.debug("static-ffmpeg fetch result: available=%s", available)
    return available


def ensure_ffmpeg() -> str:
    """Return a usable ffmpeg path, auto-fetching a static build if needed.

    Never raises — returns the best-effort path (possibly the bare
    ``"ffmpeg"`` name) so callers can emit actionable diagnostics.
    """
    path = get_ffmpeg_path()
    if _is_executable(path):
        return path
    log.debug("ffmpeg not found at %s; attempting static fallback", path)
    if _try_static_ffmpeg():
        refreshed = get_ffmpeg_path()
        if _is_executable(refreshed):
            return refreshed
        system = shutil.which("ffmpeg")
        if system:
            return system
    return path


def ensure_ffprobe() -> str:
    """Best-effort ffprobe path (fetched alongside ffmpeg by static-ffmpeg)."""
    path = get_ffprobe_path()
    if _is_executable(path):
        return path
    if _try_static_ffmpeg():
        refreshed = get_ffprobe_path()
        if _is_executable(refreshed):
            return refreshed
        system = shutil.which("ffprobe")
        if system:
            return system
    return path


def install_ffmpeg_extra(timeout: float = 300.0) -> str:
    """Install the ``pinak-cli[ffmpeg]`` extra (static-ffmpeg) via pip.

    This is the one-command FFmpeg provisioning path surfaced as
    ``pinak --install-ffmpeg`` and the ``/ffmpeg`` REPL command: it
    downloads version-pinned static FFmpeg/ffprobe builds into the user
    cache on first use — no admin rights, no system packages needed.

    Returns the resolved ffmpeg path, or ``""`` when provisioning failed
    (callers then print the manual-install guidance). Never raises.
    """
    from .subproc import run_cmd

    current = ensure_ffmpeg()
    if _is_executable(current):
        log.info("ffmpeg already available at %s", current)
        return current
    try:
        result = run_cmd(
            [sys.executable, "-m", "pip", "install", "pinak-cli[ffmpeg]"],
            timeout=timeout,
        )
    except Exception as exc:
        log.warning("pip install of pinak-cli[ffmpeg] failed: %r", exc)
        return ""
    if result.returncode != 0:
        log.warning("pip install of pinak-cli[ffmpeg] failed: %s", result.stderr)
        return ""
    if _try_static_ffmpeg():
        refreshed = ensure_ffmpeg()
        if _is_executable(refreshed):
            log.info("ffmpeg provisioned at %s", refreshed)
            return refreshed
    return ""
