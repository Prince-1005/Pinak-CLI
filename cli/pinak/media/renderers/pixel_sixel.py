"""Mode 1: DEC Sixel Graphics Protocol native pixel renderer with 256-color palette and RLE."""

from __future__ import annotations

from io import StringIO

from PIL import Image

from .base import BaseRenderer


class SixelRenderer(BaseRenderer):
    """Renders native pixel graphics using the DEC Sixel protocol with RLE compression."""

    def __init__(self, cell_width_px: int = 10, cell_height_px: int = 20) -> None:
        self.cell_width_px = max(1, int(cell_width_px))
        self.cell_height_px = max(1, int(cell_height_px))

    @property
    def mode_name(self) -> str:
        return "sixel"

    @property
    def is_pixel_native(self) -> bool:
        return True

    def render_frame(
        self,
        img: Image.Image,
        target_cols: int,
        target_rows: int,
        exact_1to1: bool = False,
    ) -> str:
        target_px_w = target_cols * self.cell_width_px
        target_px_h = target_rows * self.cell_height_px

        src_w, src_h = img.size

        if exact_1to1:
            scaled_w = min(src_w, target_px_w)
            scaled_h = min(src_h, target_px_h)
            if scaled_h % 6 != 0:
                scaled_h -= scaled_h % 6
            scaled_w = max(6, scaled_w)
            scaled_h = max(6, scaled_h)
            resized = img.crop((0, 0, scaled_w, scaled_h))
        else:
            # Maintain aspect ratio
            scale = min(target_px_w / max(1, src_w), target_px_h / max(1, src_h))
            scaled_w = max(16, int(src_w * scale))
            scaled_h = max(16, int(src_h * scale))

            # Pad height to multiple of 6 for complete sixel bands
            if scaled_h % 6 != 0:
                scaled_h += 6 - (scaled_h % 6)

            resized = img.resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)
        # FASTOCTREE is 4x-10x faster for video frames and large buffers, preventing CPU starvation
        method = (
            Image.Quantize.FASTOCTREE
            if (scaled_w * scaled_h > 120_000)
            else Image.Quantize.MEDIANCUT
        )
        quantized = resized.convert("RGB").quantize(colors=256, method=method)
        palette = quantized.getpalette() or []
        raw_pixels = quantized.tobytes()

        out = StringIO()
        # Sixel DCS header and raster attributes
        out.write(f'\x1bPq"1;1;{scaled_w};{scaled_h}')

        # Declare color palette (up to 256 colors)
        num_colors = min(256, len(palette) // 3)
        for i in range(num_colors):
            r = int((palette[i * 3] / 255.0) * 100)
            g = int((palette[i * 3 + 1] / 255.0) * 100)
            b = int((palette[i * 3 + 2] / 255.0) * 100)
            out.write(f"#{i};2;{r};{g};{b}")

        # Process 6-pixel high bands
        for band_top in range(0, scaled_h, 6):
            # For each color used in this band, build the sixel row
            active_colors: dict[int, list[int]] = {}
            for bit in range(6):
                row_idx = band_top + bit
                if row_idx >= scaled_h:
                    break
                row_offset = row_idx * scaled_w
                bit_mask = 1 << bit
                for col_idx in range(scaled_w):
                    color_idx = raw_pixels[row_offset + col_idx]
                    if color_idx not in active_colors:
                        active_colors[color_idx] = [0] * scaled_w
                    active_colors[color_idx][col_idx] |= bit_mask

            for color_idx, col_bits in active_colors.items():
                out.write(f"#{color_idx}")
                # Run-length compression
                rle_char = ""
                rle_count = 0

                for val in col_bits:
                    char = chr(63 + val)
                    if char == rle_char:
                        rle_count += 1
                    else:
                        if rle_count > 0:
                            if rle_count > 3:
                                out.write(f"!{rle_count}{rle_char}")
                            else:
                                out.write(rle_char * rle_count)
                        rle_char = char
                        rle_count = 1

                if rle_count > 0:
                    if rle_count > 3:
                        out.write(f"!{rle_count}{rle_char}")
                    else:
                        out.write(rle_char * rle_count)

                out.write("$")  # Carriage return to start of sixel line

            out.write("-")  # Move down to next 6-pixel band

        out.write("\x1b\\")  # String terminator
        return out.getvalue()
