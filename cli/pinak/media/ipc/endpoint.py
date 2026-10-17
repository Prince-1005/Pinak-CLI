"""User-scoped endpoint discovery for authenticated local media control."""

from __future__ import annotations

import itertools
import json
import os
import sys
import tempfile
from pathlib import Path

import platformdirs


def endpoint_directory() -> Path:
    return Path(platformdirs.user_cache_dir("pinak-cli", "pinak")) / "ipc"


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)  # query limited information
        if not handle:
            return ctypes.get_last_error() == 5  # access denied is not proof of death
        try:
            exit_code = wintypes.DWORD()
            return (
                bool(kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)))
                and exit_code.value == 259
            )
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def publish_endpoint(port: int, token: str) -> Path:
    directory = endpoint_directory()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        directory.chmod(0o700)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=directory, prefix=".endpoint-", delete=False
    ) as stream:
        temporary = Path(stream.name)
        json.dump({"port": port, "token": token, "pid": os.getpid()}, stream)
    try:
        temporary.chmod(0o600)
        path = directory / f"session-{port}.json"
        os.replace(temporary, path)
        return path
    finally:
        temporary.unlink(missing_ok=True)


def discover_endpoint() -> tuple[int, str]:
    """Require an unambiguous session; never silently control a different player."""
    requested = os.environ.get("PINAK_IPC_PORT")
    paths = itertools.islice(endpoint_directory().glob("session-*.json"), 128)
    candidates: list[tuple[int, str]] = []
    for path in paths:
        try:
            if path.is_symlink() or path.stat().st_size > 4096:
                continue
            if os.name != "nt" and (
                path.stat().st_uid != getattr(os, "getuid", lambda: -1)()
                or path.stat().st_mode & 0o077
            ):
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not _process_alive(int(data.get("pid", 0))):
                continue
            port, token = int(data["port"]), str(data["token"])
            if 0 < port < 65536 and token and (not requested or str(port) == requested):
                candidates.append((port, token))
        except (ValueError, KeyError, TypeError, OSError):
            continue
    if len(candidates) != 1:
        raise ConnectionError("No unique media session. Set PINAK_IPC_PORT to the player's port.")
    return candidates[0]
