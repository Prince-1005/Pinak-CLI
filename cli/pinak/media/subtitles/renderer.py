"""Subtitle text overlay renderers for GUI frame blitting and TUI terminal display."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont


class SubtitleRenderer:
    """Renders active subtitle text onto video frames or terminal canvases."""

    @classmethod
    def render_overlay_on_frame(
        cls,
        frame_img: Image.Image,
        text: str,
        font_size: int | None = None,
    ) -> Image.Image:
        """
        Renders styled, high-contrast subtitle text onto a video frame.
        Uses white text with a solid dark outline and translucent bounding pill.
        """
        if not text:
            return frame_img

        img = frame_img.copy()
        w, h = img.size
        draw = ImageDraw.Draw(img)

        # Estimate font scale relative to video height (typical mpv sub-font-size is ~4% of height)
        calc_size = font_size or max(14, int(h * 0.045))
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont
        try:
            # Try loading default scalable truetype font if available
            font = ImageFont.truetype("arial.ttf", calc_size)
        except Exception:
            try:
                font = ImageFont.load_default(size=calc_size)
            except TypeError:
                font = ImageFont.load_default()

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            return img

        # Compute bounding boxes for multiline text
        line_metrics = []
        total_text_h = 0.0
        max_line_w = 0.0

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
            line_h = bbox[3] - bbox[1]
            line_metrics.append((line, line_w, line_h))
            max_line_w = max(max_line_w, line_w)
            total_text_h += line_h + 4

        # Position at lower 12% margin from bottom
        start_y = max(10, h - total_text_h - int(h * 0.08))

        # 1. Draw translucent pill background behind subtitles
        pill_pad_x = 12
        pill_pad_y = 6
        pill_box = [
            (w - max_line_w) // 2 - pill_pad_x,
            start_y - pill_pad_y,
            (w + max_line_w) // 2 + pill_pad_x,
            start_y + total_text_h + pill_pad_y,
        ]

        # Create overlay for alpha transparency
        try:
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rounded_rectangle(pill_box, radius=6, fill=(15, 20, 28, 190))
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            img = Image.alpha_composite(img, overlay)
            draw = ImageDraw.Draw(img)
        except Exception:
            pass

        # 2. Draw text with dark drop shadow and crisp white foreground
        curr_y = start_y
        for line, line_w, line_h in line_metrics:
            x = (w - line_w) // 2
            # Drop shadow / outline
            for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1), (0, 2)):
                draw.text((x + dx, curr_y + dy), line, font=font, fill=(0, 0, 0))
            # Foreground text (high visibility bright ivory)
            draw.text((x, curr_y), line, font=font, fill=(255, 255, 240))
            curr_y += line_h + 4

        return img.convert("RGB")

    @classmethod
    def format_tui_subtitles(cls, text: str, max_cols: int) -> str:
        """
        Formats active subtitles as a high-contrast centered TUI pill string.
        """
        if not text:
            return ""

        clean_lines = [line.strip() for line in text.split("\n") if line.strip()]
        out_lines = []
        for line in clean_lines:
            truncated = line[: max(10, max_cols - 6)]
            pill = f"  {truncated}  "
            pad_left = max(0, (max_cols - len(pill)) // 2)
            out_lines.append(
                f"{' ' * pad_left}\x1b[48;2;12;16;24m\x1b[38;2;255;255;220;1m{pill}\x1b[0m"
            )

        return "\n".join(out_lines)
