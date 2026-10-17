"""Data models for subtitle cues, tracks, and styling."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from pathlib import Path


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
        # Keep cues sorted by start_sec for fast binary search
        self.cues.sort(key=lambda c: c.start_sec)
        self._start_times = [c.start_sec for c in self.cues]

    def add_cue(self, cue: SubtitleCue) -> None:
        self.cues.append(cue)
        self.cues.sort(key=lambda c: c.start_sec)
        self._start_times = [c.start_sec for c in self.cues]

    def get_active_cues(self, pts: float) -> list[SubtitleCue]:
        """Finds all active cues at the given PTS timestamp."""
        if not self.cues:
            return []

        # Find the rightmost cue with start_sec <= pts
        idx = bisect.bisect_right(self._start_times, pts)
        active: list[SubtitleCue] = []

        # Check preceding cues that may still be active (spanning across current pts)
        check_start = max(0, idx - 10)
        for i in range(check_start, min(len(self.cues), idx + 2)):
            cue = self.cues[i]
            if cue.is_active(pts):
                active.append(cue)

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
