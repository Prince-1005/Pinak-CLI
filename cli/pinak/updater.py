from __future__ import annotations

import contextlib
import importlib.metadata
import json
import shutil
import sys
import threading
import time
import urllib.request
from pathlib import Path

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


def _find_pinak_binary() -> Path | None:
    """Locate the pinak executable on Windows to work around file locks during update."""
    for name in ("pinak.exe", "pinak"):
        found = shutil.which(name)
        if found:
            p = Path(found)
            if p.is_file():
                return p

    scripts_dir = Path(sys.prefix) / ("Scripts" if sys.platform.startswith("win") else "bin")
    for name in ("pinak.exe", "pinak"):
        p = scripts_dir / name
        if p.is_file():
            return p

    if sys.argv and sys.argv[0]:
        p = Path(sys.argv[0])
        if p.is_file() and p.stem.lower() == "pinak":
            return p

    return None


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
        renamed_bin: Path | None = None
        pinak_bin: Path | None = None
        if package == PINAK_PACKAGE and sys.platform.startswith("win"):
            pinak_bin = _find_pinak_binary()
            if pinak_bin and pinak_bin.exists():
                old_target = pinak_bin.with_name(f"{pinak_bin.name}.old")
                with contextlib.suppress(OSError):
                    if old_target.exists():
                        old_target.unlink()
                try:
                    pinak_bin.rename(old_target)
                    renamed_bin = old_target
                except OSError:
                    renamed_bin = None

        try:
            result = run_cmd(
                [sys.executable, "-m", "pip", "install", "--upgrade", package],
                timeout=timeout,
            )
        except Exception as exc:
            if renamed_bin and pinak_bin and not pinak_bin.exists():
                with contextlib.suppress(OSError):
                    renamed_bin.rename(pinak_bin)
            results[package] = f"Update error: {exc}"
            continue

        if result.returncode != 0:
            if renamed_bin and pinak_bin and not pinak_bin.exists():
                with contextlib.suppress(OSError):
                    renamed_bin.rename(pinak_bin)
            err = (result.stderr or result.stdout or "").strip()
            if "winerror 32" in err.lower() or "being used by another process" in err.lower():
                results[package] = (
                    f"Update failed: {package} binary is currently in use on Windows.\n"
                    f"Please exit Pinak (/exit) and run in your terminal:\n"
                    f"  pip install --upgrade {package}"
                )
            else:
                results[package] = f"Update failed. Error:\n{result.stderr}"
            continue

        if renamed_bin:
            if pinak_bin and not pinak_bin.exists():
                with contextlib.suppress(OSError):
                    renamed_bin.rename(pinak_bin)
            else:
                with contextlib.suppress(OSError):
                    renamed_bin.unlink()

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
