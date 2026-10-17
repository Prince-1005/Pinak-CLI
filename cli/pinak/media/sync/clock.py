"""Master Audio Clock reference implementation."""

from __future__ import annotations

import time

from ..decoders.audio_backend import AudioPlayerBackend


class MasterAudioClock:
    """Provides high-precision monotonic master timestamp anchored to the audio hardware DAC."""

    def __init__(self, audio_backend: AudioPlayerBackend | None = None) -> None:
        self.audio_backend = audio_backend
        self._manual_offset: float = 0.0
        self._start_perf: float = time.perf_counter()
        self._is_paused: bool = False

    def get_time(self) -> float:
        """Returns the current master presentation timestamp (PTS) in seconds."""
        if self.audio_backend is not None:
            return self.audio_backend.get_clock()

        if self._is_paused:
            return self._manual_offset

        return self._manual_offset + (time.perf_counter() - self._start_perf)

    def set_time(self, timestamp_sec: float) -> None:
        """Resets the clock to a specific timestamp."""
        self._manual_offset = max(0.0, timestamp_sec)
        self._start_perf = time.perf_counter()
        if self.audio_backend is not None:
            self.audio_backend.seek(self._manual_offset)

    def pause(self) -> None:
        if not self._is_paused:
            self._manual_offset = self.get_time()
            self._is_paused = True
            if self.audio_backend is not None:
                self.audio_backend.pause()

    def resume(self) -> None:
        if self._is_paused:
            self._start_perf = time.perf_counter()
            self._is_paused = False
            if self.audio_backend is not None:
                self.audio_backend.resume()
