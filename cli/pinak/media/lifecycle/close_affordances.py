"""Close buttons and mouse hit-testing for TUI media panels."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ClickableRegion:
    """Represents a mouse-interactive rectangular region on the terminal canvas."""

    id: str
    min_col: int
    max_col: int
    min_row: int
    max_row: int
    on_click: Callable[[], None]


class CloseAffordanceManager:
    """Manages hit-testing and action dispatching for on-screen close buttons."""

    def __init__(self, on_close: Callable[[], None]) -> None:
        self.on_close = on_close
        self.regions: list[ClickableRegion] = []

    def update_layout(self, total_cols: int, total_rows: int) -> None:
        """Recalculates button coordinates based on terminal dimensions."""
        self.regions.clear()

        # 2. Control Bar Action Button: [ ✕ Close Media ] at bottom-right
        close_btn_w = 18
        self.regions.append(
            ClickableRegion(
                id="footer_close_media",
                min_col=max(1, total_cols - close_btn_w - 2),
                max_col=total_cols,
                min_row=max(1, total_rows - 2),
                max_row=max(1, total_rows - 2),
                on_click=self.on_close,
            )
        )

    def handle_click(self, col: int, row: int) -> bool:
        """Evaluates mouse click coordinates. Returns True if a close button was clicked."""
        for r in self.regions:
            if r.min_col <= col <= r.max_col and r.min_row <= row <= r.max_row:
                r.on_click()
                return True
        return False
