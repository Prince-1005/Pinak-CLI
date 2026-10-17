"""Base interface for all terminal media renderers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from PIL import Image


class BaseRenderer(ABC):
    """Abstract base renderer interface for transforming images into terminal escape streams."""

    @property
    @abstractmethod
    def mode_name(self) -> str:
        """Returns the identifier for this rendering mode."""
        pass

    @property
    @abstractmethod
    def is_pixel_native(self) -> bool:
        """Returns True if the renderer uses hardware terminal pixel graphics (Kitty/Sixel/iTerm2)."""
        pass

    @abstractmethod
    def render_frame(
        self,
        img: Image.Image,
        target_cols: int,
        target_rows: int,
        exact_1to1: bool = False,
    ) -> str:
        """
        Renders a PIL Image to a terminal escape string formatted for the viewport bounds.
        If exact_1to1 is True, renders sub-pixels 1:1 without downsampling or stretching.
        """
        pass

    def render_braille(
        self,
        img: Image.Image,
        target_cols: int,
        target_rows: int,
        exact_1to1: bool = False,
    ) -> str:
        """
        Renders an Ultra-HD 2x4 Braille Micro-Matrix representation of the image.
        Default implementation gracefully falls back to render_frame().
        """
        return self.render_frame(img, target_cols, target_rows, exact_1to1=exact_1to1)
