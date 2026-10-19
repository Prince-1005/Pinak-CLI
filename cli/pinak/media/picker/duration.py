"""Bounded background duration lookup for the selected local media file."""

from __future__ import annotations

import math
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from ...subproc import run_cmd
from ...utils import get_ffprobe_path


def probe_duration(path: Path) -> float | None:
    """Read duration without extracting artwork or provisioning binaries."""
    result = run_cmd(
        [
            get_ffprobe_path(),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout=3.0,
    )
    try:
        duration = float(result.stdout.strip()) if result.returncode == 0 else 0.0
        if math.isfinite(duration) and duration > 0:
            return duration
    except ValueError:
        pass
    try:
        from mutagen import File

        media = File(path)
        duration = float(media.info.length) if media is not None else 0.0
        if math.isfinite(duration) and duration > 0:
            return duration
    except Exception:
        pass
    return None


class DurationInspector:
    """Only one outstanding probe; stale selections never build up a work queue."""

    def __init__(self) -> None:
        self._executor: ThreadPoolExecutor | None = None
        self._pending: tuple[tuple[Path, int, int], Future[float | None]] | None = None
        self._cache: dict[tuple[Path, int, int], float | None] = {}

    def read(self, path: Path) -> str:
        if self._pending and self._pending[1].done():
            key, future = self._pending
            try:
                self._cache[key] = future.result()
            except Exception:
                self._cache[key] = None
            self._pending = None
            if len(self._cache) > 128:
                del self._cache[next(iter(self._cache))]
        try:
            stat = path.stat()
            key = (path, stat.st_size, stat.st_mtime_ns)
        except OSError:
            return "Unavailable"
        if key in self._cache:
            duration = self._cache[key]
            if duration is None:
                return "Unavailable"
            seconds = int(duration)
            hours, seconds = divmod(seconds, 3600)
            minutes, seconds = divmod(seconds, 60)
            return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"
        if self._pending is None:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="pinak-inspector"
                )
            self._pending = (key, self._executor.submit(probe_duration, path))
        return "Loading..."

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
