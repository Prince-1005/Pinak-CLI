"""Terminal viewport scaling and cell aspect ratio compensator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScaledViewport:
    """Calculated target dimensions and letterbox padding."""

    width: int
    height: int
    pad_left: int
    pad_top: int


class ViewportScaler:
    """Computes aspect-ratio preserved dimensions and padding for terminal grids."""

    DEFAULT_CELL_RATIO = 2.0  # Terminal cells are typically ~10x20px (height is 2x width)

    @classmethod
    def calculate_halfblock_viewport(
        cls,
        src_w: int,
        src_h: int,
        cols: int,
        rows: int,
        cell_ratio: float = DEFAULT_CELL_RATIO,
        allow_upscale: bool = False,
    ) -> ScaledViewport:
        """
        Calculates half-block canvas bounds.
        In half-block mode, each character cell contains 2 vertical pixels.
        Since cells are ~1:2 ratio, 1 col x 2 vertical half-blocks is approximately a 1:1 square!
        Virtual pixel canvas: width = cols, height = rows * 2.
        """
        if src_w <= 0 or src_h <= 0 or cols <= 0 or rows <= 0:
            return ScaledViewport(
                width=max(1, cols), height=max(2, rows * 2), pad_left=0, pad_top=0
            )

        max_virt_w = cols
        max_virt_h = max(2, int(rows * cell_ratio))

        scale = min(max_virt_w / src_w, max_virt_h / src_h)
        if not allow_upscale:
            scale = min(1.0, scale)

        scaled_w = max(1, int(src_w * scale))
        scaled_h = max(2, int(src_h * scale))

        # Ensure height is even for pairing top/bottom half-blocks
        if scaled_h % 2 != 0:
            scaled_h -= 1
        scaled_h = max(2, scaled_h)

        pad_left = max(0, (cols - scaled_w) // 2)
        # Vertical pad in cell rows (each cell row contains 2 half-blocks)
        equiv_cell_rows = max(1, scaled_h // 2)
        pad_top_cells = max(0, (rows - equiv_cell_rows) // 2)

        return ScaledViewport(
            width=scaled_w,
            height=scaled_h,
            pad_left=pad_left,
            pad_top=pad_top_cells,
        )

    @classmethod
    def calculate_ascii_viewport(
        cls,
        src_w: int,
        src_h: int,
        cols: int,
        rows: int,
        cell_ratio: float = DEFAULT_CELL_RATIO,
        allow_upscale: bool = False,
    ) -> ScaledViewport:
        """
        Calculates ASCII canvas bounds.
        In ASCII mode, 1 cell = 1 character. To prevent vertical stretching from 1:2 cells,
        effective vertical height is adjusted by 1 / cell_ratio.
        """
        if src_w <= 0 or src_h <= 0 or cols <= 0 or rows <= 0:
            return ScaledViewport(width=max(1, cols), height=max(1, rows), pad_left=0, pad_top=0)

        # Correct for cell aspect ratio
        src_aspect = src_w / max(1.0, float(src_h))

        # Scale to fit inside cols and rows
        scaled_w = cols
        scaled_h = int(scaled_w / (src_aspect * cell_ratio))

        if scaled_h > rows:
            scaled_h = rows
            scaled_w = int(scaled_h * (src_aspect * cell_ratio))

        if not allow_upscale:
            actual_w = src_w
            actual_h = int(src_h / cell_ratio)
            if scaled_w > actual_w or scaled_h > actual_h:
                scale_down = min(actual_w / scaled_w, actual_h / scaled_h)
                scaled_w = max(1, int(scaled_w * scale_down))
                scaled_h = max(1, int(scaled_h * scale_down))

        scaled_w = max(1, min(cols, scaled_w))
        scaled_h = max(1, min(rows, scaled_h))

        pad_left = max(0, (cols - scaled_w) // 2)
        pad_top = max(0, (rows - scaled_h) // 2)

        return ScaledViewport(
            width=scaled_w,
            height=scaled_h,
            pad_left=pad_left,
            pad_top=pad_top,
        )

    @classmethod
    def calculate_quadrant_viewport(
        cls,
        src_w: int,
        src_h: int,
        cols: int,
        rows: int,
        cell_ratio: float = DEFAULT_CELL_RATIO,
        allow_upscale: bool = False,
    ) -> ScaledViewport:
        """
        Calculates 2x2 quadrant sub-pixel canvas bounds.
        Each character cell holds 2 horizontal sub-pixels and 2 vertical sub-pixels.
        To preserve physical aspect ratio on terminal cells (with height/width = cell_ratio):
        target W_sub / H_sub = (src_w / src_h) * cell_ratio.
        """
        if src_w <= 0 or src_h <= 0 or cols <= 0 or rows <= 0:
            return ScaledViewport(
                width=max(2, cols * 2), height=max(2, rows * 2), pad_left=0, pad_top=0
            )

        max_virt_w = cols * 2
        max_virt_h = rows * 2

        sub_aspect = (src_w / max(1.0, float(src_h))) * cell_ratio

        if not allow_upscale:
            scale = min(1.0, max_virt_w / (src_h * sub_aspect), max_virt_h / src_h)
            scaled_h = max(2, int(src_h * scale))
            scaled_w = max(2, int(scaled_h * sub_aspect))
        else:
            scaled_w = max_virt_w
            scaled_h = int(scaled_w / max(0.001, sub_aspect))
            if scaled_h > max_virt_h:
                scaled_h = max_virt_h
                scaled_w = int(scaled_h * sub_aspect)

        scaled_w = max(2, min(max_virt_w, scaled_w))
        scaled_h = max(2, min(max_virt_h, scaled_h))

        # Ensure both dimensions are even (2x2 sub-pixels per cell)
        if scaled_w % 2 != 0:
            scaled_w -= 1
        if scaled_h % 2 != 0:
            scaled_h -= 1
        scaled_w = max(2, scaled_w)
        scaled_h = max(2, scaled_h)

        used_cols = scaled_w // 2
        used_rows = scaled_h // 2

        pad_left = max(0, (cols - used_cols) // 2)
        pad_top = max(0, (rows - used_rows) // 2)

        return ScaledViewport(
            width=scaled_w,
            height=scaled_h,
            pad_left=pad_left,
            pad_top=pad_top,
        )

    @classmethod
    def calculate_braille_viewport(
        cls,
        src_w: int,
        src_h: int,
        cols: int,
        rows: int,
        cell_ratio: float = DEFAULT_CELL_RATIO,
        allow_upscale: bool = False,
    ) -> ScaledViewport:
        """
        Calculates 2x4 Braille sub-pixel micro-matrix canvas bounds.
        Each character cell holds 2 horizontal dots and 4 vertical dots.
        With standard terminal cells having height/width = cell_ratio (default 2.0):
        dot width = W/2, dot height = (W*cell_ratio)/4 = W/2 (when cell_ratio=2.0).
        Thus Braille sub-pixels are naturally 1:1 square!
        Effective dot aspect ratio = (src_w / src_h) * (cell_ratio / 2.0).
        Prevents vertical stretching and preserves the exact original shape of photos.
        """
        if src_w <= 0 or src_h <= 0 or cols <= 0 or rows <= 0:
            return ScaledViewport(
                width=max(2, cols * 2), height=max(4, rows * 4), pad_left=0, pad_top=0
            )

        max_virt_w = cols * 2
        max_virt_h = rows * 4

        dot_aspect = (src_w / max(1.0, float(src_h))) * (cell_ratio / 2.0)

        if not allow_upscale:
            actual_h = max(1, int(src_h * (2.0 / cell_ratio)))
            scale = min(
                1.0,
                max_virt_w / max(1.0, float(src_w)),
                max_virt_h / max(1.0, float(actual_h)),
            )
            scaled_w = max(2, int(src_w * scale))
            scaled_h = max(4, int(actual_h * scale))
        else:
            scaled_w = max_virt_w
            scaled_h = int(scaled_w / max(0.001, dot_aspect))
            if scaled_h > max_virt_h:
                scaled_h = max_virt_h
                scaled_w = int(scaled_h * dot_aspect)

        scaled_w = max(2, min(max_virt_w, scaled_w))
        scaled_h = max(4, min(max_virt_h, scaled_h))

        # Ensure dimensions align to Braille cell boundaries: 2 horizontal dots, 4 vertical dots
        if scaled_w % 2 != 0:
            scaled_w -= 1
        if scaled_h % 4 != 0:
            scaled_h -= scaled_h % 4
        scaled_w = max(2, scaled_w)
        scaled_h = max(4, scaled_h)

        used_cols = scaled_w // 2
        used_rows = scaled_h // 4

        pad_left = max(0, (cols - used_cols) // 2)
        pad_top = max(0, (rows - used_rows) // 2)

        return ScaledViewport(
            width=scaled_w,
            height=scaled_h,
            pad_left=pad_left,
            pad_top=pad_top,
        )
