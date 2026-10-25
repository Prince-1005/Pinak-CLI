"""Data models for subtitle cues, tracks, and styling."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from pathlib import Path

from ...text_safety import safe_text


@dataclass
class SubtitleCue:
    """Represents a single timed subtitle entry."""

    index: int
    start_sec: float
    end_sec: float
    text: str

    def is_active(self, pts: float) -> bool:
        """Checks if this cue should be displayed at presentation timestamp (PTS)."""
        return self.start_sec <= pts <= self.end_sec


@dataclass
class SubtitleTrack:
    """Represents an embedded or external subtitle track."""

    track_id: int
    title: str = "Default"
    language: str = "und"
    cues: list[SubtitleCue] = field(default_factory=list)
    is_external: bool = False
    file_path: Path | None = None

    def __post_init__(self) -> None:
        self.title = safe_text(self.title)
        # Keep cues sorted by start_sec for fast binary search
        self.cues.sort(key=lambda c: c.start_sec)
        self._start_times = [c.start_sec for c in self.cues]
        self._max_end_times = self._prefix_max_ends()

    def _prefix_max_ends(self) -> list[float]:
        maximum = float("-inf")
        result = []
        for cue in self.cues:
            maximum = max(maximum, cue.end_sec)
            result.append(maximum)
        return result

    def add_cue(self, cue: SubtitleCue) -> None:
        self.cues.append(cue)
        self.cues.sort(key=lambda c: c.start_sec)
        self._start_times = [c.start_sec for c in self.cues]
        self._max_end_times = self._prefix_max_ends()

    def get_active_cues(self, pts: float) -> list[SubtitleCue]:
        """Finds all active cues at the given PTS timestamp."""
        if not self.cues:
            return []

        # Find the rightmost cue with start_sec <= pts
        idx = bisect.bisect_right(self._start_times, pts)
        active: list[SubtitleCue] = []

        # Prefix maxima let us stop as soon as no earlier cue can still overlap.
        for i in range(idx - 1, -1, -1):
            if self._max_end_times[i] < pts:
                break
            cue = self.cues[i]
            if cue.is_active(pts):
                active.append(cue)

        active.reverse()
        return active

    def get_cue_at(self, pts: float) -> SubtitleCue | None:
        """Returns the first active cue at given PTS, or None."""
        cues = self.get_active_cues(pts)
        return cues[0] if cues else None

    def get_active_text(self, pts: float) -> str:
        """Returns joined active subtitle text at given PTS."""
        cues = self.get_active_cues(pts)
        return "\n".join(c.text for c in cues)

    @property
    def label(self) -> str:
        """User-friendly display label for this subtitle track."""
        if self.title and self.title != "Default":
            return self.title
        if self.language and self.language != "und":
            return f"Track {self.track_id} ({self.language})"
        return f"Track #{self.track_id}"
