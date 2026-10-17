"""Single background subtitle worker; optional extraction never gates playback."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from .model import SubtitleTrack
from .parser import SubtitleParser

logger = logging.getLogger("pinak.media.subtitles")


class SubtitleLoader:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._generation = 0
        self._job: tuple[int, Path] | None = None
        self._result: list[SubtitleTrack] | None = None
        self._closed = False
        self._worker: threading.Thread | None = None

    def load(self, path: Path) -> None:
        with self._lock:
            if self._closed:
                return
            self._generation += 1
            self._job = (self._generation, path)
            self._result = None
            if self._worker is None:
                self._worker = threading.Thread(
                    target=self._run, daemon=True, name="PinakSubtitles"
                )
                self._worker.start()
            self._wake.set()

    def clear(self) -> None:
        with self._lock:
            self._generation += 1
            self._job = None
            self._result = None

    def poll(self) -> list[SubtitleTrack] | None:
        with self._lock:
            result, self._result = self._result, None
            return result

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._generation += 1
            self._job = None
            self._result = None
            self._wake.set()

    def _run(self) -> None:
        while True:
            self._wake.wait()
            with self._lock:
                if self._closed:
                    return
                job, self._job = self._job, None
                self._wake.clear()
            if job is None:
                continue
            generation, path = job

            def cancelled(current_generation: int = generation) -> bool:
                return self._closed or current_generation != self._generation

            try:
                tracks = SubtitleParser.discover_sibling_subtitles(path)
                tracks.extend(
                    SubtitleParser.extract_embedded_subtitles(
                        path,
                        is_cancelled=cancelled,
                    )
                )
            except Exception as exc:
                logger.debug("Optional subtitle loading failed: %s", exc)
                tracks = []
            with self._lock:
                if self._closed:
                    return
                if generation == self._generation:
                    self._result = tracks
