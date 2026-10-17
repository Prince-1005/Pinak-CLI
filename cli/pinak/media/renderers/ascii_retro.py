"""Retro / Classic ASCII character density renderer with phosphor color profiles."""

from __future__ import annotations

from typing import Literal

from PIL import Image

from .base import BaseRenderer
from .pixels import rgb_pixels
from .scaler import ViewportScaler


class ASCIIRenderer(BaseRenderer):
    """Renders images using calibrated character density ramps and phosphor color palettes."""

    # 70-level high-precision luminance ramp
    RAMP_70 = "$@B%8&WM#*oahkbdpqwmZO0QLCJUXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. "
    RAMP_10 = " .:-=+*#%@"

    PHOSPHOR_COLORS = {
        "green": "\x1b[38;2;0;255;70m",
        "amber": "\x1b[38;2;255;176;0m",
        "white": "\x1b[38;2;220;220;220m",
    }

    def __init__(
        self,
        color_profile: Literal["truecolor", "green", "amber", "white"] = "truecolor",
        use_short_ramp: bool = False,
    ) -> None:
        self.color_profile = color_profile
        self.ramp = self.RAMP_10 if use_short_ramp else self.RAMP_70

    @property
    def mode_name(self) -> str:
        return "ascii"

    @property
    def is_pixel_native(self) -> bool:
        return False

    def render_frame(
        self,
        img: Image.Image,
        target_cols: int,
        target_rows: int,
        exact_1to1: bool = False,
    ) -> str:
        src_w, src_h = img.size
        vp = ViewportScaler.calculate_ascii_viewport(
            src_w, src_h, target_cols, target_rows, allow_upscale=False
        )

        if src_w == vp.width and src_h == vp.height:
            resized = img.convert("RGB")
        else:
            resized = img.resize((vp.width, vp.height), Image.Resampling.LANCZOS).convert("RGB")
        pixels = rgb_pixels(resized)

        lines: list[str] = []

        # Top padding lines
        for _ in range(vp.pad_top):
            lines.append(" " * target_cols)

        left_pad = " " * vp.pad_left
        right_pad = " " * max(0, target_cols - vp.pad_left - vp.width)

        ramp_len = len(self.ramp)

        # Static color prefix for phosphor modes
        phosphor_prefix = self.PHOSPHOR_COLORS.get(self.color_profile, "")

        for y in range(vp.height):
            row_parts: list[str] = [left_pad]
            if phosphor_prefix:
                row_parts.append(phosphor_prefix)

            last_fg: tuple[int, int, int] = (-1, -1, -1)

            for x in range(vp.width):
                r, g, b = pixels[x, y]
                # ITU-R BT.601 perceived luminance
                lum = (0.299 * r) + (0.587 * g) + (0.114 * b)
                # Map luminance [0, 255] to ramp index [ramp_len - 1, 0] (dark to light)
                norm_idx = int((lum / 255.0) * (ramp_len - 1))
                char = self.ramp[ramp_len - 1 - norm_idx]

                if self.color_profile == "truecolor":
                    fg = (r, g, b)
                    if fg != last_fg:
                        row_parts.append(f"\x1b[38;2;{r};{g};{b}m")
                        last_fg = fg

                row_parts.append(char)

            row_parts.append("\x1b[0m")
            row_parts.append(right_pad)
            lines.append("".join(row_parts))

        remaining = target_rows - len(lines)
        for _ in range(max(0, remaining)):
            lines.append(" " * target_cols)

        return "\n".join(lines[:target_rows])
