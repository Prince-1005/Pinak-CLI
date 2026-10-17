"""High-Density Unicode Quadrant Block (2x2 sub-pixels per cell) 24-bit TrueColor renderer."""

from __future__ import annotations

from PIL import Image

from .base import BaseRenderer
from .pixels import rgb_pixels
from .scaler import ViewportScaler

# Complete 16-character Unicode Block Elements quadrant lookup table.
# Bit assignments:
# Bit 3 (8): Top-Left (TL)
# Bit 2 (4): Top-Right (TR)
# Bit 1 (2): Bottom-Left (BL)
# Bit 0 (1): Bottom-Right (BR)
QUADRANT_CHARS: tuple[str, ...] = (
    " ",  # 0000: Empty space (background only)
    "\u2597",  # 0001: Quadrant lower right (▗)
    "\u2596",  # 0010: Quadrant lower left (▖)
    "\u2584",  # 0011: Lower half block (▄)
    "\u259d",  # 0100: Quadrant upper right (▝)
    "\u2590",  # 0101: Right half block (▐)
    "\u259e",  # 0110: Quadrant upper right and lower left (▞)
    "\u259f",  # 0111: Quadrant upper right, lower left and lower right (▟)
    "\u2598",  # 1000: Quadrant upper left (▘)
    "\u259a",  # 1001: Quadrant upper left and lower right (▚)
    "\u258c",  # 1010: Left half block (▌)
    "\u2599",  # 1011: Quadrant upper left, lower left and lower right (▙)
    "\u2580",  # 1100: Upper half block (▀)
    "\u259c",  # 1101: Quadrant upper left, upper right and lower right (▜)
    "\u259b",  # 1110: Quadrant upper left, upper right and lower left (▛)
    "\u2588",  # 1111: Full block (█)
)


class QuadrantRenderer(BaseRenderer):
    """Renders images using 2x2 Unicode quadrant blocks, doubling horizontal terminal resolution."""

    def __init__(self, dither_mode: str = "none") -> None:
        self.dither_mode = dither_mode

    @property
    def mode_name(self) -> str:
        return "quadrant"

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

        vp = ViewportScaler.calculate_quadrant_viewport(
            src_w, src_h, target_cols, target_rows, allow_upscale=False
        )

        if src_w == vp.width and src_h == vp.height:
            resized = img.convert("RGB")
        else:
            resized = img.resize((vp.width, vp.height), Image.Resampling.LANCZOS).convert("RGB")

        try:
            from PIL import ImageEnhance

            enhancer = ImageEnhance.Sharpness(resized)
            resized = enhancer.enhance(1.20)
            c_enhancer = ImageEnhance.Contrast(resized)
            resized = c_enhancer.enhance(1.06)
        except Exception:
            pass
        vp_w = vp.width
        vp_h = vp.height
        used_cols = vp.width // 2
        pad_left = vp.pad_left
        pad_top = vp.pad_top

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
        right_pad_str = " " * max(0, target_cols - pad_left - used_cols)

        # Iterate over character cells (each cell is 2x2 sub-pixels)
        for y in range(0, vp_h, 2):
            row_parts: list[str] = [left_pad_str]
            last_fg: tuple[int, int, int] = (-1, -1, -1)
            last_bg: tuple[int, int, int] = (-1, -1, -1)

            for x in range(0, vp_w, 2):
                p0 = pixels[x, y]  # Top-Left (TL)
                p1 = pixels[x + 1, y]  # Top-Right (TR)
                p2 = pixels[x, y + 1]  # Bottom-Left (BL)
                p3 = pixels[x + 1, y + 1]  # Bottom-Right (BR)

                # Fast check for solid color cells
                if p0 == p1 == p2 == p3:
                    glyph = " "
                    fg = p0
                    bg = p0
                else:
                    # 2-color optimal clustering of 4 sub-pixels
                    d01 = abs(p0[0] - p1[0]) + abs(p0[1] - p1[1]) + abs(p0[2] - p1[2])
                    d02 = abs(p0[0] - p2[0]) + abs(p0[1] - p2[1]) + abs(p0[2] - p2[2])
                    d03 = abs(p0[0] - p3[0]) + abs(p0[1] - p3[1]) + abs(p0[2] - p3[2])
                    d12 = abs(p1[0] - p2[0]) + abs(p1[1] - p2[1]) + abs(p1[2] - p2[2])
                    d13 = abs(p1[0] - p3[0]) + abs(p1[1] - p3[1]) + abs(p1[2] - p3[2])
                    d23 = abs(p2[0] - p3[0]) + abs(p2[1] - p3[1]) + abs(p2[2] - p3[2])

                    max_d = d01
                    seed_a, seed_b = p0, p1
                    if d02 > max_d:
                        max_d, seed_a, seed_b = d02, p0, p2
                    if d03 > max_d:
                        max_d, seed_a, seed_b = d03, p0, p3
                    if d12 > max_d:
                        max_d, seed_a, seed_b = d12, p1, p2
                    if d13 > max_d:
                        max_d, seed_a, seed_b = d13, p1, p3
                    if d23 > max_d:
                        max_d, seed_a, seed_b = d23, p2, p3

                    if max_d <= 12:
                        glyph = " "
                        avg_col = (
                            (p0[0] + p1[0] + p2[0] + p3[0]) // 4,
                            (p0[1] + p1[1] + p2[1] + p3[1]) // 4,
                            (p0[2] + p1[2] + p2[2] + p3[2]) // 4,
                        )
                        fg = avg_col
                        bg = avg_col
                    else:
                        mask = 0
                        fg_r = fg_g = fg_b = fg_cnt = 0
                        bg_r = bg_g = bg_b = bg_cnt = 0

                        pts = (p0, p1, p2, p3)
                        shifts = (3, 2, 1, 0)
                        for pt, shift in zip(pts, shifts, strict=True):
                            da = (
                                abs(pt[0] - seed_a[0])
                                + abs(pt[1] - seed_a[1])
                                + abs(pt[2] - seed_a[2])
                            )
                            db = (
                                abs(pt[0] - seed_b[0])
                                + abs(pt[1] - seed_b[1])
                                + abs(pt[2] - seed_b[2])
                            )
                            if da <= db:
                                mask |= 1 << shift
                                fg_r += pt[0]
                                fg_g += pt[1]
                                fg_b += pt[2]
                                fg_cnt += 1
                            else:
                                bg_r += pt[0]
                                bg_g += pt[1]
                                bg_b += pt[2]
                                bg_cnt += 1

                        fg = (
                            (fg_r // fg_cnt, fg_g // fg_cnt, fg_b // fg_cnt)
                            if fg_cnt > 0
                            else seed_a
                        )
                        bg = (bg_r // bg_cnt, bg_g // bg_cnt, bg_b // bg_cnt) if bg_cnt > 0 else fg

                        glyph = QUADRANT_CHARS[mask]

                # ANSI escape code delta deduplication
                if glyph == " ":
                    if bg != last_bg:
                        row_parts.append(f"\x1b[48;2;{bg[0]};{bg[1]};{bg[2]}m")
                        last_bg = bg
                    row_parts.append(" ")
                elif glyph == "\u2588":
                    if fg != last_fg:
                        row_parts.append(f"\x1b[38;2;{fg[0]};{fg[1]};{fg[2]}m")
                        last_fg = fg
                    row_parts.append("\u2588")
                else:
                    if fg != last_fg:
                        row_parts.append(f"\x1b[38;2;{fg[0]};{fg[1]};{fg[2]}m")
                        last_fg = fg
                    if bg != last_bg:
                        row_parts.append(f"\x1b[48;2;{bg[0]};{bg[1]};{bg[2]}m")
                        last_bg = bg
                    row_parts.append(glyph)

            row_parts.append("\x1b[0m")
            row_parts.append(right_pad_str)
            lines.append("".join(row_parts))

        # Bottom padding lines
        remaining_rows = target_rows - len(lines)
        for _ in range(max(0, remaining_rows)):
            lines.append(" " * target_cols)

        return "\n".join(lines[:target_rows])
