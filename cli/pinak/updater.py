from __future__ import annotations

import importlib.metadata
import json
import sys
import threading
import time
import urllib.request

from .config import config, save_config

UPDATE_AVAILABLE: str | None = None
UPDATE_PACKAGE = "yt-dlp"

PINAK_UPDATE_AVAILABLE: str | None = None
PINAK_PACKAGE = "pinak-cli"

_CHECK_INTERVAL = 86400  # 24 hours


def _parse_version(v: str) -> tuple[int, ...]:
    # Compare versions (yt-dlp versions are usually like "2023.11.16")
    return tuple(int(p) for p in v.split(".") if p.isdigit())


def _fetch_latest_version(package: str, timeout: float = 5.0) -> str | None:
    """Return the latest version string of *package* from PyPI, or None."""
    req = urllib.request.Request(
        f"https://pypi.org/pypi/{package}/json",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    # Fixed HTTPS PyPI endpoint — no user-controlled scheme. nosec B310
    with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
        data = json.loads(response.read().decode("utf-8"))
    version = data.get("info", {}).get("version")
    return str(version) if version else None


def _installed_version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def _current_pinak_version() -> str:
    from . import __version__

    installed = _installed_version(PINAK_PACKAGE)
    return installed or __version__


def _check_update_thread() -> None:
    global UPDATE_AVAILABLE, PINAK_UPDATE_AVAILABLE
    try:
        last_check = float(config.get("last_update_check", 0.0))
        current_time = time.time()

        # Check at most once every 24 hours.
        if current_time - last_check < _CHECK_INTERVAL:
            return

        latest_ytdlp = _fetch_latest_version(UPDATE_PACKAGE)
        if latest_ytdlp:
            current_ytdlp = _installed_version(UPDATE_PACKAGE)
            if current_ytdlp and _parse_version(latest_ytdlp) > _parse_version(current_ytdlp):
                UPDATE_AVAILABLE = latest_ytdlp

        latest_pinak = _fetch_latest_version(PINAK_PACKAGE)
        if latest_pinak:
            current_pinak = _current_pinak_version()
            if _parse_version(latest_pinak) > _parse_version(current_pinak):
                PINAK_UPDATE_AVAILABLE = latest_pinak

        config["last_update_check"] = current_time
        save_config()
    except Exception:
        # Silently fail, it's a background daemon task
        pass


def start_background_update_check() -> None:
    t = threading.Thread(target=_check_update_thread, daemon=True)
    t.start()


def _package_version(package: str) -> str | None:
    """Installed version of *package* (pinak itself falls back to __version__)."""
    if package == PINAK_PACKAGE:
        return _current_pinak_version()
    return _installed_version(package)


def perform_update(timeout: float = 300.0) -> dict[str, str]:
    """Upgrade yt-dlp and pinak-cli itself via pip.

    Returns a mapping of package name → human-readable result message.
    A real version bump is reported as ``"Updated <pkg> <old> → <new>"``
    (callers look for the ``→`` to decide whether a restart is needed);
    an already-current package reports ``"already the latest"``.
    Success clears the cached ``*_UPDATE_AVAILABLE`` flags. Never raises:
    failures are reported as message strings so callers can print them.
    """
    global UPDATE_AVAILABLE, PINAK_UPDATE_AVAILABLE
    from .subproc import run_cmd

    results: dict[str, str] = {}
    for package in (UPDATE_PACKAGE, PINAK_PACKAGE):
        before = _package_version(package)
        try:
            result = run_cmd(
                [sys.executable, "-m", "pip", "install", "--upgrade", package],
                timeout=timeout,
            )
        except Exception as exc:
            results[package] = f"Update error: {exc}"
            continue
        if result.returncode != 0:
            results[package] = f"Update failed. Error:\n{result.stderr}"
            continue
        if package == UPDATE_PACKAGE:
            UPDATE_AVAILABLE = None
        else:
            PINAK_UPDATE_AVAILABLE = None
        after = _package_version(package)
        if before and after and _parse_version(after) > _parse_version(before):
            results[package] = f"Updated {package} {before} → {after}."
        else:
            results[package] = f"{package} is already the latest ({after or before})."
    return results
