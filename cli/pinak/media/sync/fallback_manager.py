"""Multi-tier fallback manager for graphics protocols, decoders, and audio drivers."""

from __future__ import annotations

import logging

from ..core.terminal_caps import TerminalCapabilities
from ..renderers.ascii_retro import ASCIIRenderer
from ..renderers.base import BaseRenderer
from ..renderers.halfblock import HalfBlockRenderer
from ..renderers.pixel_iterm2 import ITerm2Renderer
from ..renderers.pixel_kitty import KittyRenderer
from ..renderers.pixel_sixel import SixelRenderer
from ..renderers.quadrant import QuadrantRenderer

logger = logging.getLogger("pinak.media.fallback")


class FallbackManager:
    """Orchestrates graceful degradation across terminal rendering protocols."""

    @classmethod
    def get_best_renderer(
        cls, caps: TerminalCapabilities, media_type: str = "video"
    ) -> BaseRenderer:
        """Selects the highest-fidelity renderer supported by the host terminal."""
        if caps.has_kitty:
            logger.info("Terminal supports Kitty Graphics Protocol (Mode 1)")
            return KittyRenderer()

        if caps.has_sixel:
            logger.info("Terminal supports DEC Sixel Graphics (Mode 1)")
            return SixelRenderer(
                cell_width_px=caps.cell_width_px, cell_height_px=caps.cell_height_px
            )

        if caps.has_iterm2:
            logger.info("Terminal supports iTerm2 Inline Images (Mode 1)")
            return ITerm2Renderer()

        if caps.has_truecolor:
            if media_type == "picture":
                logger.info(
                    "Terminal supports 24-bit TrueColor High-Density Quadrant (2x2 sub-pixels)"
                )
                return QuadrantRenderer()
            logger.info("Terminal supports 24-bit TrueColor Unicode Half-Block (Mode 2)")
            return HalfBlockRenderer()

        return ASCIIRenderer(color_profile="white", use_short_ramp=True)

    @classmethod
    def degrade_renderer(cls, current: BaseRenderer) -> BaseRenderer:
        """Degrades renderer to the next lower tier upon protocol error."""
        current_mode = current.mode_name
        logger.warning(f"Degrading renderer from mode '{current_mode}'")

        if current_mode in ("kitty", "sixel", "iterm2"):
            return HalfBlockRenderer()

        if current_mode == "quadrant":
            return HalfBlockRenderer()

        if current_mode == "halfblock":
            return ASCIIRenderer(color_profile="white")

        return ASCIIRenderer(use_short_ramp=True)
