"""Universal Unicode Upper Half-Block (▀, U+2580) 24-bit TrueColor renderer with ANSI deduplication."""

from __future__ import annotations

from PIL import Image

from .base import BaseRenderer
from .pixels import rgb_pixels
from .scaler import ViewportScaler


class HalfBlockRenderer(BaseRenderer):
    """Renders images using upper half-block characters (▀) with ANSI 24-bit RGB escape codes."""

    def __init__(self, dither_mode: str = "none") -> None:
        self.dither_mode = dither_mode

    @property
    def mode_name(self) -> str:
        return "halfblock"

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

        vp = ViewportScaler.calculate_halfblock_viewport(
            src_w, src_h, target_cols, target_rows, allow_upscale=False
        )
        vp_w = vp.width
        vp_h = vp.height
        pad_left = vp.pad_left
        pad_top = vp.pad_top

        # Scale image to virtual half-block resolution with high-fidelity LANCZOS resampling
        if src_w == vp_w and src_h == vp_h:
            resized = img.convert("RGB")
        else:
            resized = img.resize((vp_w, vp_h), Image.Resampling.LANCZOS).convert("RGB")

        try:
            from PIL import ImageEnhance

            # Apply refined clarity and color vibrance to pop on terminal displays
            enhancer = ImageEnhance.Sharpness(resized)
            resized = enhancer.enhance(1.25)
            c_enhancer = ImageEnhance.Contrast(resized)
            resized = c_enhancer.enhance(1.08)
            col_enhancer = ImageEnhance.Color(resized)
            resized = col_enhancer.enhance(1.12)
        except Exception:
            pass

        # Apply spatial color quantization and dithering if enabled
        if self.dither_mode == "fs":
            from .dither import ColorQuantizer

            resized = ColorQuantizer.floyd_steinberg_dither(resized)
        elif self.dither_mode == "bayer":
            from .dither import ColorQuantizer

            resized = ColorQuantizer.ordered_bayer_dither(resized)

        pixels = rgb_pixels(resized)

        lines: list[str] = []

        # Top padding lines
        for _ in range(pad_top):
            lines.append(" " * target_cols)

        left_pad_str = " " * pad_left
        right_pad_str = " " * max(0, target_cols - pad_left - vp_w)

        # Process two vertical pixel rows per character row
        for y in range(0, vp_h, 2):
            row_parts: list[str] = [left_pad_str]
            last_fg: tuple[int, int, int] = (-1, -1, -1)
            last_bg: tuple[int, int, int] = (-1, -1, -1)

            for x in range(vp_w):
                fg = pixels[x, y]  # Top pixel (Foreground)
                bg = pixels[x, y + 1]  # Bottom pixel (Background)

                # ANSI escape code delta deduplication
                if fg != last_fg:
                    row_parts.append(f"\x1b[38;2;{fg[0]};{fg[1]};{fg[2]}m")
                    last_fg = fg
                if bg != last_bg:
                    row_parts.append(f"\x1b[48;2;{bg[0]};{bg[1]};{bg[2]}m")
                    last_bg = bg

                row_parts.append("▀")

            row_parts.append("\x1b[0m")  # Reset at end of row
            row_parts.append(right_pad_str)
            lines.append("".join(row_parts))

        # Bottom padding lines
        remaining_rows = target_rows - len(lines)
        for _ in range(max(0, remaining_rows)):
            lines.append(" " * target_cols)

        return "\n".join(lines[:target_rows])
