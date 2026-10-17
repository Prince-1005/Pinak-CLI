"""Mode 1: Kitty Graphics Protocol native pixel renderer with 2x4 Braille Micro-Matrix fallback."""

from __future__ import annotations

import base64
import os
from io import BytesIO

import numpy as np
from PIL import Image

from .base import BaseRenderer
from .scaler import ViewportScaler


class KittyRenderer(BaseRenderer):
    """Renders pixel-perfect images via Kitty Graphics APC or Ultra-HD 2x4 Braille Micro-Matrix."""

    CHUNK_SIZE = 4096

    # 2x4 Braille dot weights ordered by (y, x):
    # (0, 0): 0x01 | (0, 1): 0x08
    # (1, 0): 0x02 | (1, 1): 0x10
    # (2, 0): 0x04 | (2, 1): 0x20
    # (3, 0): 0x40 | (3, 1): 0x80
    BRAILLE_WEIGHTS = np.array([0x01, 0x08, 0x02, 0x10, 0x04, 0x20, 0x40, 0x80], dtype=np.uint16)

    @classmethod
    def is_kitty_supported(cls) -> bool:
        """Detects if the host terminal natively executes Kitty Graphics Protocol APC codes."""
        env = os.environ
        if bool(env.get("PINAK_FORCE_KITTY_APC")):
            return True
        if bool(env.get("KITTY_WINDOW_ID")) or bool(env.get("KITTY_PID")):
            return True
        if bool(env.get("GHOSTTY_RESOURCES_DIR")) or bool(env.get("WEZTERM_PANE")):
            return True
        term = env.get("TERM", "").lower()
        if "kitty" in term or "ghostty" in term:
            return True
        term_prog = env.get("TERM_PROGRAM", "").lower()
        return term_prog in ("kitty", "ghostty", "wezterm")

    @property
    def mode_name(self) -> str:
        return "kitty"

    @property
    def is_pixel_native(self) -> bool:
        return True

    @property
    def is_native_active(self) -> bool:
        return self.is_kitty_supported()

    def render_native_kitty(
        self,
        img: Image.Image,
        target_cols: int,
        target_rows: int,
    ) -> str:
        """Encodes and emits Kitty Graphics Protocol APC escape sequence."""
        src_w, src_h = img.size
        vp = ViewportScaler.calculate_halfblock_viewport(
            src_w, src_h, target_cols, target_rows, allow_upscale=False
        )
        used_cols = max(1, vp.width)
        used_rows = max(1, vp.height // 2)

        bio = BytesIO()
        rgb_img = img.convert("RGBA")
        rgb_img.save(bio, format="PNG", optimize=False)
        png_bytes = bio.getvalue()

        b64_payload = base64.b64encode(png_bytes).decode("ascii")
        chunks = [
            b64_payload[i : i + self.CHUNK_SIZE]
            for i in range(0, len(b64_payload), self.CHUNK_SIZE)
        ]

        if not chunks:
            return ""

        parts: list[str] = []
        for idx, chunk in enumerate(chunks):
            is_last = idx == len(chunks) - 1
            m = 0 if is_last else 1
            if idx == 0:
                header = f"\x1b_Ga=T,f=100,c={used_cols},r={used_rows},m={m};{chunk}\x1b\\"
            else:
                header = f"\x1b_Gm={m};{chunk}\x1b\\"
            parts.append(header)

        vertical_advance = "\n" * max(1, used_rows - 1)
        return "".join(parts) + vertical_advance

    def render_braille(
        self,
        img: Image.Image,
        target_cols: int,
        target_rows: int,
        exact_1to1: bool = False,
    ) -> str:
        """
        Renders an Ultra-High-Definition 2x4 Braille Micro-Matrix (8 subpixels per character cell)
        with 24-bit TrueColor foreground. Preserves exact physical aspect ratio and original shape
        without vertical stretching, perfectly centering the photo with letterbox / pillarbox padding.
        """
        if target_cols <= 0 or target_rows <= 0:
            return ""

        src_w, src_h = img.size
        vp = ViewportScaler.calculate_braille_viewport(
            src_w, src_h, target_cols, target_rows, allow_upscale=False
        )
        vp_w = vp.width
        vp_h = vp.height
        used_cols = vp_w // 2
        used_rows = vp_h // 4
        pad_left = vp.pad_left
        pad_top = vp.pad_top
        if src_w == vp_w and src_h == vp_h:
            resized = img.convert("RGB")
        else:
            resized = img.convert("RGB").resize((vp_w, vp_h), Image.Resampling.BILINEAR)

        arr = np.asarray(resized, dtype=np.float32)

        # Reshape to (used_rows, used_cols, 8 subpixels, 3 RGB channels)
        dots = (
            arr.reshape(used_rows, 4, used_cols, 2, 3)
            .transpose(0, 2, 1, 3, 4)
            .reshape(used_rows, used_cols, 8, 3)
        )

        # Luminance per subpixel: 0.299R + 0.587G + 0.114B
        lum = 0.299 * dots[..., 0] + 0.587 * dots[..., 1] + 0.114 * dots[..., 2]

        # Dot activation threshold (subpixel lights up when luminance > 55.0)
        active = lum > 55.0
        masks = (active.astype(np.uint16) * self.BRAILLE_WEIGHTS).sum(axis=-1)

        # Mean RGB of active dots, falling back to cell mean
        active_counts = active.sum(axis=-1, keepdims=True)
        sum_rgb = (dots * active[..., None]).sum(axis=-2)
        cell_mean_rgb = dots.mean(axis=-2)
        safe_counts = np.maximum(active_counts, 1)
        avg_rgb = np.where(active_counts > 0, sum_rgb / safe_counts, cell_mean_rgb).astype(np.uint8)

        lines: list[str] = []
        pad_str = " " * pad_left
        for r in range(target_rows):
            if r < pad_top or r >= pad_top + used_rows:
                lines.append("\x1b[2K" + " " * target_cols)
                continue

            img_r = r - pad_top
            line_parts = ["\x1b[2K", pad_str]
            for c in range(used_cols):
                mask = int(masks[img_r, c])
                red, green, blue = avg_rgb[img_r, c]
                if mask > 0:
                    char = chr(0x2800 + mask)
                    line_parts.append(f"\x1b[38;2;{red};{green};{blue}m{char}")
                else:
                    cell_lum = 0.299 * red + 0.587 * green + 0.114 * blue
                    if cell_lum > 22.0:
                        line_parts.append(f"\x1b[38;2;{red};{green};{blue}m⠂")
                    else:
                        line_parts.append(" ")
            line_parts.append("\x1b[0m")
            right_pad = max(0, target_cols - pad_left - used_cols)
            if right_pad > 0:
                line_parts.append(" " * right_pad)
            lines.append("".join(line_parts))

        return "\n".join(lines)

    def render_frame(
        self,
        img: Image.Image,
        target_cols: int,
        target_rows: int,
        exact_1to1: bool = False,
        force_native: bool = False,
    ) -> str:
        return self.render_native_kitty(img, target_cols, target_rows)
