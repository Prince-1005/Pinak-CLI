"""Display mode coordinator: Enforces clean, distraction-free Fullscreen layout."""

from __future__ import annotations

import warnings
from dataclasses import dataclass


@dataclass
class ViewportPartition:
    canvas_cols: int
    canvas_rows: int
    sidebar_cols: int = 0
    is_mini: bool = False


class DisplayModeCoordinator:
    """[DEPRECATED] Manages dedicated Fullscreen terminal layout without mini/max fragmentation."""

    def __init__(self) -> None:
        warnings.warn(
            "DisplayModeCoordinator is deprecated and will be removed in a future release. "
            "Media layout is managed directly by MediaSession and ViewportScaler.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.mode: str = "fullscreen"

    @property
    def is_mini_screen(self) -> bool:
        return False

    def toggle(self) -> str:
        """Mini/max toggle is removed; layout remains in robust fullscreen."""
        return "fullscreen"

    def partition_terminal(self, total_cols: int, total_rows: int) -> ViewportPartition:
        """Allocates 100% of the terminal canvas to active media playback."""
        effective_rows = max(4, total_rows - 2)  # Exclude header and footer
        return ViewportPartition(
            canvas_cols=total_cols,
            canvas_rows=effective_rows,
            sidebar_cols=0,
            is_mini=False,
        )
