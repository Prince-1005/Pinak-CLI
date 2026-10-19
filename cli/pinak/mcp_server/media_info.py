"""Time-bounded metadata helper, isolated from the MCP protocol process."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .policy import ToolFailure


def inspect_media(path: Path) -> dict[str, Any]:
    process = subprocess.Popen(  # nosec B603: fixed module, approved local file only
        [sys.executable, "-m", "pinak.mcp_server.media_info", str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        cwd=Path.home(),
        start_new_session=os.name != "nt",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        output, _ = process.communicate(timeout=12)
    except subprocess.TimeoutExpired as exc:
        if sys.platform != "win32":
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()  # helper Job Object owns FFprobe descendants
        process.communicate(timeout=2)
        raise ToolFailure("METADATA_TIMEOUT", "Metadata probe exceeded its time limit.") from exc
    if process.returncode or len(output.encode()) > 32768:
        raise ToolFailure(
            "METADATA_FAILED",
            "Local metadata could not be read within probe limits.",
            "Check the file and FFprobe availability with doctor.",
        )
    return dict(json.loads(output))


def main() -> None:
    from ..media.decoders.probe import MediaProbe
    from .worker import protect_windows_children

    job = protect_windows_children()

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
