"""High-fidelity color quantization and spatial dithering (Floyd-Steinberg & Bayer)."""

from __future__ import annotations

from PIL import Image

from .pixels import rgb_pixels


class ColorQuantizer:
    """Provides spatial error-diffusion and ordered threshold dithering for terminal imagery."""

    # Standard 4x4 Bayer threshold matrix normalized to [0, 1]
    BAYER_4X4 = [
        [0.0 / 16.0, 8.0 / 16.0, 2.0 / 16.0, 10.0 / 16.0],
        [12.0 / 16.0, 4.0 / 16.0, 14.0 / 16.0, 6.0 / 16.0],
        [3.0 / 16.0, 11.0 / 16.0, 1.0 / 16.0, 9.0 / 16.0],
        [15.0 / 16.0, 7.0 / 16.0, 13.0 / 16.0, 5.0 / 16.0],
    ]

    @classmethod
    def floyd_steinberg_dither(cls, img: Image.Image, levels_per_channel: int = 16) -> Image.Image:
        """
        Applies 2D Floyd-Steinberg error diffusion dithering across RGB color planes.
        Breaks up banding artifacts in gradients and dark scenes.
        """
        rgb_img = img.convert("RGB")
        w, h = rgb_img.size
        if w <= 1 or h <= 1:
            return rgb_img

        # Work with floating point RGB buffers for precision
        step = 255.0 / max(2, levels_per_channel - 1)

        # Try fast vector path using PIL palette quantization if available
        try:
            # Use PIL's optimized C-level Floyd-Steinberg dithering with web/adaptive palette
            return rgb_img.quantize(
                colors=min(256, levels_per_channel**3),
                method=Image.Quantize.MEDIANCUT,
                dither=Image.Dither.FLOYDSTEINBERG,
            ).convert("RGB")
        except Exception:
            pass

        # Pure-Python spatial error diffusion fallback
        pixels = list(rgb_img.getdata())
        r_buf = [float(p[0]) for p in pixels]
        g_buf = [float(p[1]) for p in pixels]
        b_buf = [float(p[2]) for p in pixels]

        def clamp(v: float) -> int:
            return max(0, min(255, int(v)))

        for y in range(h):
            for x in range(w):
                idx = y * w + x
                old_r = r_buf[idx]
                old_g = g_buf[idx]
                old_b = b_buf[idx]

                new_r = round(old_r / step) * step
                new_g = round(old_g / step) * step
                new_b = round(old_b / step) * step

                r_buf[idx] = new_r
                g_buf[idx] = new_g
                b_buf[idx] = new_b

                err_r = old_r - new_r
                err_g = old_g - new_g
                err_b = old_b - new_b

                # Distribute error: 7/16 (x+1, y), 3/16 (x-1, y+1), 5/16 (x, y+1), 1/16 (x+1, y+1)
                if x + 1 < w:
                    r_buf[idx + 1] += err_r * (7.0 / 16.0)
                    g_buf[idx + 1] += err_g * (7.0 / 16.0)
                    b_buf[idx + 1] += err_b * (7.0 / 16.0)
                if y + 1 < h:
                    if x > 0:
                        r_buf[idx + w - 1] += err_r * (3.0 / 16.0)
                        g_buf[idx + w - 1] += err_g * (3.0 / 16.0)
                        b_buf[idx + w - 1] += err_b * (3.0 / 16.0)
                    r_buf[idx + w] += err_r * (5.0 / 16.0)
                    g_buf[idx + w] += err_g * (5.0 / 16.0)
                    b_buf[idx + w] += err_b * (5.0 / 16.0)
                    if x + 1 < w:
                        r_buf[idx + w + 1] += err_r * (1.0 / 16.0)
                        g_buf[idx + w + 1] += err_g * (1.0 / 16.0)
                        b_buf[idx + w + 1] += err_b * (1.0 / 16.0)

        out_img = Image.new("RGB", (w, h))
        out_pixels = [(clamp(r_buf[i]), clamp(g_buf[i]), clamp(b_buf[i])) for i in range(w * h)]
        out_img.putdata(out_pixels)
        return out_img

    @classmethod
    def ordered_bayer_dither(cls, img: Image.Image, spread: float = 16.0) -> Image.Image:
        """
        Applies 4x4 ordered Bayer matrix dithering.
        Extremely fast, deterministic, and ideal for high-FPS video streams.
        """
        rgb_img = img.convert("RGB")
        w, h = rgb_img.size
        out = Image.new("RGB", (w, h))

        src_pixels = rgb_pixels(rgb_img)
        dst_pixels = rgb_pixels(out)
        matrix = cls.BAYER_4X4

        for y in range(h):
            row_matrix = matrix[y % 4]
            for x in range(w):
                threshold = (row_matrix[x % 4] - 0.5) * spread
                r, g, b = src_pixels[x, y]
                new_r = max(0, min(255, int(r + threshold)))
                new_g = max(0, min(255, int(g + threshold)))
                new_b = max(0, min(255, int(b + threshold)))
                dst_pixels[x, y] = (new_r, new_g, new_b)

        return out
