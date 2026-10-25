"""Finish a Windows self-update after the Pinak launcher has exited."""

from __future__ import annotations

import ctypes
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil

PACKAGE = "pinak-cli"
WAIT_SECONDS = 24 * 60 * 60


def wait_for_process_exit(pid: int, timeout_seconds: int = WAIT_SECONDS) -> bool:
    """Wait on the actual Windows process handle, avoiding PID reuse races."""
    if not sys.platform.startswith("win"):
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = ctypes.c_int
    handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        return ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER: already exited
    try:
        return kernel32.WaitForSingleObject(handle, timeout_seconds * 1000) == 0
    finally:
        kernel32.CloseHandle(handle)


def write_status(path: Path, state: str, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(
            {
                "state": state,
                "message": message[:2000],
                "time": time.time(),
                "pid": os.getpid(),
                "process_started": psutil.Process(os.getpid()).create_time(),
            }
        ),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _stage_rollback_wheel(directory: Path) -> Path | None:
    """Keep the installed release locally before replacing the environment."""
    try:
        previous = importlib.metadata.version(PACKAGE)
    except importlib.metadata.PackageNotFoundError:
        return None
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--no-deps",
            "--only-binary=:all:",
            "--dest",
            str(directory),
            f"{PACKAGE}=={previous}",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        return None
    return next(directory.glob("pinak_cli-*.whl"), None)


def _restore_previous(wheel: Path) -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-deps", "--force-reinstall", str(wheel)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def finish_update(parent_pids: list[int], status_path: Path) -> None:
    if not all(wait_for_process_exit(pid) for pid in parent_pids):
        write_status(status_path, "failed", "Pinak did not exit before the update deadline.")
        return
    with tempfile.TemporaryDirectory(prefix="pinak-update-rollback-") as staging:
        previous = _stage_rollback_wheel(Path(staging))
        if previous is None:
            write_status(
                status_path,
                "failed",
                "Pinak update did not start because the installed release could not be staged "
                "for rollback. Repair the package source and retry.",
            )
            return
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", PACKAGE],
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            if result.returncode:
                raise RuntimeError(f"pip exit code {result.returncode}")
            installed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import importlib.metadata; print(importlib.metadata.version('pinak-cli'))",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if installed.returncode or not installed.stdout.strip():
                raise RuntimeError("installed version could not be verified")
            write_status(
                status_path,
                "succeeded",
                f"Pinak update finished. Installed version: {installed.stdout.strip()}.",
            )
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
            restored = _restore_previous(previous)
            write_status(
                status_path,
                "failed",
                f"Pinak update failed: {exc}. "
                + (
                    "Previous release restored."
                    if restored
                    else "Rollback failed; reinstall the previous release manually."
                ),
            )


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    try:
        parent_pids = [int(value) for value in sys.argv[1].split(",")]
        if not parent_pids or any(pid <= 0 for pid in parent_pids):
            return 2
        status = Path(sys.argv[2])
        write_status(status, "waiting", "Waiting for Pinak to exit before updating.")
        finish_update(parent_pids, status)
    except (OSError, ValueError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
