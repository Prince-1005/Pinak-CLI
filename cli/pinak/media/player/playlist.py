"""Playlist manager with random selection, played-track tracking, and back-history."""

from __future__ import annotations

import random
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal


class PlaylistManager:
    """Manages audio and video playlists with shuffle and repeat modes."""

    def __init__(
        self,
        tracks: Sequence[str | Path] | list[Any],
        initial_index: int = 0,
        repeat_mode: Literal["solo", "all", "none"] = "none",
    ) -> None:
        self.original_playlist = [Path(p).resolve() for p in tracks if Path(p).is_file()]
        self.history_stack: list[int] = []
        self.current_idx = (
            max(0, min(len(self.original_playlist) - 1, initial_index))
            if self.original_playlist
            else 0
        )
        self.is_shuffled = False
        self.repeat_mode: Literal["solo", "all", "none"] = repeat_mode
        self._played_indices = {self.current_idx} if self.original_playlist else set()

    @property
    def total_tracks(self) -> int:
        return len(self.original_playlist)

    def get_current(self) -> Path | None:
        if not self.original_playlist:
            return None
        return self.original_playlist[self.current_idx]

    def toggle_shuffle(self) -> bool:
        """Keep the playing track and played history while toggling random selection."""
        self.is_shuffled = not self.is_shuffled
        return self.is_shuffled

    def _remaining_indices(self) -> list[int]:
        return [
            index
            for index in range(self.total_tracks)
            if index not in self._played_indices and index != self.current_idx
        ]

    def cycle_repeat_mode(self) -> str:
        """Cycles repeat mode: 'none' (OFF) -> 'all' -> 'solo' -> 'none'."""
        if self.repeat_mode == "none":
            self.repeat_mode = "all"
        elif self.repeat_mode == "all":
            self.repeat_mode = "solo"
        else:
            self.repeat_mode = "none"
        return self.repeat_mode

    def has_next(self) -> bool:
        """Determines if another track is available for playback under active repeat mode."""
        if not self.original_playlist:
            return False
        if self.repeat_mode in ("solo", "all"):
            return True
        if self.is_shuffled:
            return bool(self._remaining_indices())
        return self.current_idx + 1 < len(self.original_playlist)

    def next_track(self, *, wrap: bool = False, manual: bool = False) -> Path | None:
        """Advance, optionally wrapping music playlists independently of repeat mode."""
        if not self.original_playlist:
            return None

        if self.repeat_mode == "solo" and not manual:
            return self.get_current()

        self._played_indices.add(self.current_idx)
        if self.is_shuffled:
            candidates = (
                list(range(self.total_tracks))
                if self.repeat_mode in ("all", "solo")
                else self._remaining_indices()
            )
            if not candidates:
                return None
            next_idx = random.choice(candidates)
        else:
            next_idx = self.current_idx + 1
            if next_idx >= self.total_tracks:
                if wrap or self.repeat_mode == "all":
                    next_idx = 0
                else:
                    return None

        self.history_stack.append(self.current_idx)
        if len(self.history_stack) > 1024:
            del self.history_stack[:-1024]
        self.current_idx = next_idx
        self._played_indices.add(self.current_idx)
        return self.get_current()

    def prev_track(self, *, wrap: bool = False) -> Path | None:
        """Return to the previous track, honoring shuffle history and optional wrap."""
        if not self.original_playlist:
            return None

        if self.is_shuffled:
            if self.history_stack:
                self.current_idx = self.history_stack.pop()
                self._played_indices.add(self.current_idx)
            return self.get_current()

        if wrap and self.current_idx == 0:
            self.current_idx = len(self.original_playlist) - 1
            self.history_stack.clear()
            return self.get_current()

        if self.history_stack:
            self.current_idx = self.history_stack.pop()
            return self.get_current()

        if self.current_idx <= 0:
            if self.repeat_mode == "all":
                self.current_idx = len(self.original_playlist) - 1
            else:
                self.current_idx = 0
            return self.get_current()

        self.current_idx -= 1
        return self.get_current()
