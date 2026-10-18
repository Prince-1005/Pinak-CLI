"""Playlist manager supporting Fisher-Yates shuffle with back-history and repeat modes."""

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
        self.shuffled_indices = list(range(len(self.original_playlist)))
        self.history_stack: list[int] = []
        self.current_idx = (
            max(0, min(len(self.original_playlist) - 1, initial_index))
            if self.original_playlist
            else 0
        )
        self.is_shuffled = False
        self.repeat_mode: Literal["solo", "all", "none"] = repeat_mode

    @property
    def total_tracks(self) -> int:
        return len(self.original_playlist)

    def get_current(self) -> Path | None:
        if not self.original_playlist:
            return None
        idx = self.shuffled_indices[self.current_idx] if self.is_shuffled else self.current_idx
        return self.original_playlist[idx]

    def toggle_shuffle(self) -> bool:
        """Toggles Fisher-Yates shuffle mode."""
        current = self.get_current()
        self.is_shuffled = not self.is_shuffled
        if self.is_shuffled and self.original_playlist:
            n = len(self.shuffled_indices)
            for i in range(n - 1, 0, -1):
                j = random.randint(0, i)
                self.shuffled_indices[i], self.shuffled_indices[j] = (
                    self.shuffled_indices[j],
                    self.shuffled_indices[i],
                )
            # Reset history on reshuffle
            self.history_stack.clear()
        if current is not None:
            original_idx = self.original_playlist.index(current)
            self.current_idx = (
                self.shuffled_indices.index(original_idx) if self.is_shuffled else original_idx
            )
        self.history_stack.clear()
        return self.is_shuffled

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
        return self.current_idx + 1 < len(self.original_playlist)

    def next_track(self, *, wrap: bool = False, manual: bool = False) -> Path | None:
        """Advance, optionally wrapping music playlists independently of repeat mode."""
        if not self.original_playlist:
            return None

        if self.repeat_mode == "solo" and not manual:
            return self.get_current()

        self.history_stack.append(self.current_idx)
        if len(self.history_stack) > 1024:
            del self.history_stack[:-1024]
        self.current_idx += 1

        if self.current_idx >= len(self.original_playlist):
            if wrap or self.repeat_mode == "all":
                self.current_idx = 0
            else:
                self.current_idx = len(self.original_playlist) - 1
                return None  # Reached end of playlist under 'none' mode

        return self.get_current()

    def prev_track(self, *, wrap: bool = False) -> Path | None:
        """Return to the previous track, honoring shuffle history and optional wrap."""
        if not self.original_playlist:
            return None

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
