from __future__ import annotations

import contextlib
import importlib.metadata
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import psutil
from filelock import FileLock
from filelock import Timeout as FileLockTimeout

from .config import CONFIG_FILE, config, save_config

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


def _update_status_path() -> Path:
    return Path(CONFIG_FILE).with_name("update-result.json")


def _status_worker_live(prior: dict[str, object]) -> bool:
    state = prior.get("state")
    if state == "pending":
        return time.time() - float(prior.get("time", 0)) < 10
    if state != "waiting":
        return False
    try:
        pid = int(prior["pid"])
        started = float(prior["process_started"])
        return abs(psutil.Process(pid).create_time() - started) < 1
    except (KeyError, TypeError, ValueError, psutil.Error, OSError):
        return False


def _schedule_windows_pinak_update() -> str:
    """Wait until this launcher exits before upgrading its own environment."""
    status = _update_status_path()
    status.parent.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(str(status) + ".lock", timeout=10):
            return _schedule_windows_pinak_update_locked(status)
    except FileLockTimeout:
        return "Another update is being scheduled. Wait briefly and retry."


def _schedule_windows_pinak_update_locked(status: Path) -> str:
    from .update_worker import write_status

    try:
        prior = json.loads(status.read_text(encoding="utf-8"))
        if _status_worker_live(prior):
            return "Pinak update is already queued. Exit Pinak with /exit and wait for completion."
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    pids = [os.getpid()]
    try:
        parent = psutil.Process(os.getpid()).parent()
        if parent and parent.name().casefold() == "pinak.exe":
            pids.append(parent.pid)
    except (psutil.Error, OSError):
        pass
    process: subprocess.Popen[bytes] | None = None
    try:
        write_status(status, "pending", "Waiting for Pinak to exit before updating.")
        process = subprocess.Popen(  # nosec B603
            [
                sys.executable,
                "-m",
                "pinak.update_worker",
                ",".join(str(pid) for pid in pids),
                str(status),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                state = json.loads(status.read_text(encoding="utf-8")).get("state")
                if state == "waiting":
                    break
                if state == "failed":
                    raise OSError("The update helper failed to initialize")
            except (ValueError, AttributeError, TypeError):
                pass
            if process.poll() is not None:
                raise OSError("The update helper exited before it was ready")
            time.sleep(0.05)
        else:
            raise OSError("The update helper did not become ready")
    except OSError as exc:
        if process is not None and process.poll() is None:
            with contextlib.suppress(OSError):
                process.terminate()
        with contextlib.suppress(OSError):
            write_status(status, "failed", f"Could not start update helper: {exc}")
        command = subprocess.list2cmdline(
            [sys.executable, "-m", "pip", "install", "--upgrade", PINAK_PACKAGE]
        )
        return f"Could not start the Windows update helper. Exit Pinak and run:\n  {command}"
    return (
        "Pinak update is queued. Exit Pinak with /exit, wait for it to finish, "
        "then start Pinak again. The result will appear on the next launch."
    )


def take_update_result() -> dict[str, str] | None:
    """Read a completed deferred update once; keep pending status for the next launch."""
    status = _update_status_path()
    try:
        data = json.loads(status.read_text(encoding="utf-8"))
        if data.get("state") not in {"succeeded", "failed"}:
            return None
        status.unlink()
        return {"state": str(data["state"]), "message": str(data.get("message", ""))}
    except (OSError, ValueError, AttributeError):
        return None


def perform_update(timeout: float = 300.0) -> dict[str, str]:
    """Upgrade yt-dlp now; defer Pinak itself until exit on Windows.

    Returns a mapping of package name → human-readable result message.
    A real version bump is reported as ``"Updated <pkg> <old> → <new>"``
    (callers look for the ``→`` to decide whether a restart is needed);
    an already-current package reports ``"already the latest"``.
    Success clears the cached ``*_UPDATE_AVAILABLE`` flags. Windows Pinak
    updates retain the notice until their detached helper reports completion.
    """
    global UPDATE_AVAILABLE, PINAK_UPDATE_AVAILABLE
    from .subproc import run_cmd

    results: dict[str, str] = {}
    for package in (UPDATE_PACKAGE, PINAK_PACKAGE):
        before = _package_version(package)
        if package == PINAK_PACKAGE and sys.platform.startswith("win"):
            try:
                latest = _fetch_latest_version(package)
            except (OSError, ValueError):
                latest = None
            if latest and before and _parse_version(latest) <= _parse_version(before):
                PINAK_UPDATE_AVAILABLE = None
                results[package] = f"{package} is already the latest ({before})."
            else:
                results[package] = _schedule_windows_pinak_update()
            continue

        try:
            result = run_cmd(
                [sys.executable, "-m", "pip", "install", "--upgrade", package],
                timeout=timeout,
            )
        except Exception as exc:
            results[package] = f"Update error: {exc}"
            continue

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            results[package] = f"Update failed. Error:\n{err}"
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
