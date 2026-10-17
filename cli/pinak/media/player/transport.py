"""Media transport controller for playback, seek, volume, and progress bar generation."""

from __future__ import annotations

from collections.abc import Callable


class TransportController:
    """Manages playback state, timeline seeking (±10s), volume adjustments, and progress bars."""

    def __init__(self, duration_sec: float = 0.0) -> None:
        self.duration_sec = max(0.0, duration_sec)
        self.current_pts: float = 0.0
        self.is_playing: bool = True
        self.volume: float = 1.0  # Range: 0.0 to 1.5
        self.is_muted: bool = False
        self.on_seek: Callable[[float], None] | None = None

    def toggle_play_pause(self) -> bool:
        self.is_playing = not self.is_playing
        return self.is_playing

    def seek_relative(self, delta_sec: float) -> float:
        """Seeks forward or backward by delta_sec (e.g. +10s or -10s)."""
        target = max(0.0, self.current_pts + delta_sec)
        if self.duration_sec > 0:
            target = min(self.duration_sec, target)
        self.current_pts = target
        if self.on_seek:
            self.on_seek(target)
        return self.current_pts

    def seek_to(self, target_sec: float) -> float:
        """Direct seek to specific timestamp."""
        target = max(0.0, target_sec)
        if self.duration_sec > 0:
            target = min(self.duration_sec, target)
        self.current_pts = target
        if self.on_seek:
            self.on_seek(target)
        return self.current_pts

    def seek_absolute(self, target_sec: float) -> float:
        """Alias for seek_to for absolute seek requests."""
        return self.seek_to(target_sec)

    def volume_up(self, step: float = 0.05) -> float:
        self.volume = min(1.5, self.volume + step)
        return self.volume

    def volume_down(self, step: float = 0.05) -> float:
        self.volume = max(0.0, self.volume - step)
        return self.volume

    def toggle_mute(self) -> bool:
        self.is_muted = not self.is_muted
        return self.is_muted

    @staticmethod
    def format_time(seconds: float) -> str:
        """Formats floating-point seconds into MM:SS or HH:MM:SS."""
        s = max(0, int(seconds))
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def get_progress_bar(self, width: int = 40) -> str:
        """Generates a Unicode timeline scrubber progress bar with right-aligned duration."""
        safe_width = max(15, width - 2)
        cur_str = self.format_time(self.current_pts)
        dur_str = self.format_time(self.duration_sec) if self.duration_sec > 0 else "--:--"

        # Scrubber bar width
        bar_len = max(5, safe_width - len(cur_str) - len(dur_str) - 4)
        if self.duration_sec <= 0:
            bar = "━" * bar_len
            return f" {cur_str} {bar} {dur_str} "

        frac = max(0.0, min(1.0, self.current_pts / self.duration_sec))
        filled_len = int(frac * bar_len)
        empty_len = max(0, bar_len - filled_len - 1)

        bar = f"{'━' * filled_len}╸{'━' * empty_len}"
        return f" {cur_str} {bar} {dur_str} "
