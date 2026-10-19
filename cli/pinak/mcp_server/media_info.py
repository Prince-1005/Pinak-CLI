"""Time-bounded metadata helper, isolated from the MCP protocol process."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import threading
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

import psutil

from .policy import ToolFailure
from .worker_controller import terminate_owned

PROBE_TIMEOUT_SECONDS = 12


def helper_identity(output: str | bytes | None, token: str) -> tuple[int, float] | None:
    try:
        text = (
            output.decode("utf-8", errors="replace") if isinstance(output, bytes) else output or ""
        )
        identity = json.loads(text.partition("\n")[0])
        if identity["token"] == token and type(identity["pid"]) is int:
            return identity["pid"], float(identity["started"])
    except (ValueError, KeyError, TypeError):
        pass
    return None


def inspect_media(path: Path) -> dict[str, Any]:
    token = uuid.uuid4().hex
    process = subprocess.Popen(  # nosec B603: fixed module, approved local file only
        [sys.executable, "-m", "pinak.mcp_server.media_info", str(path), token],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        cwd=Path.home(),
        start_new_session=os.name != "nt",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        output, _ = process.communicate(timeout=PROBE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        identity = helper_identity(exc.output, token)
        if identity:
            # Venv launchers and their actual Python PID differ on Windows.
            # The helper reports its identity before touching untrusted media.
            terminate_owned(*identity, token)
        if sys.platform != "win32":
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()  # helper Job Object owns FFprobe descendants
        process.communicate(timeout=2)
        raise ToolFailure("METADATA_TIMEOUT", "Metadata probe exceeded its time limit.") from exc
    if process.returncode or len(output.encode()) > 32768 or not helper_identity(output, token):
        raise ToolFailure(
            "METADATA_FAILED",
            "Local metadata could not be read within probe limits.",
            "Check the file and FFprobe availability with doctor.",
        )
    return dict(json.loads(output.partition("\n")[2]))


def main() -> None:
    from ..media.decoders.probe import MediaProbe
    from .worker import protect_windows_children

    job = protect_windows_children()
    print(
        json.dumps(
            {"token": sys.argv[2], "pid": os.getpid(), "started": psutil.Process().create_time()}
        ),
        flush=True,
    )

    def expire() -> None:
        if sys.platform != "win32":
            os.killpg(os.getpgrp(), signal.SIGKILL)
        os._exit(124)  # Windows closes the Job Object even on hard exit

    deadline = threading.Timer(10, expire)
    deadline.daemon = True
    deadline.start()
    try:
        result = asdict(
            MediaProbe.probe(Path(sys.argv[1]), allow_provision=False, include_artwork=False)
        )
        result.pop("album_art_bytes", None)
        result["file_path"] = str(result["file_path"])
        result = {
            key: value[:2048] if isinstance(value, str) and key != "file_path" else value
            for key, value in result.items()
        }
        print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        deadline.cancel()
        # Keep the Windows handle alive until this process exits.
        _ = job


if __name__ == "__main__":
    main()
