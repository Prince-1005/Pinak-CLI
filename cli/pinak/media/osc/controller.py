"""mpv-style On-Screen Controller (OSC) and floating HUD overlay."""

from __future__ import annotations

import time
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont


@dataclass
class OSCState:
    """State snapshot passed to the On-Screen Controller for rendering."""

    title: str
    current_pts: float
    duration_sec: float
    is_playing: bool
    volume: float  # 0.0 to 1.5
    is_muted: bool
    subtitle_track_name: str  # e.g. "English", "Embedded #1", or "Off"
    quality_label: str  # e.g. "1080p", "Auto-Fit"
    renderer_mode: str  # e.g. "HALFBLOCK", "KITTY"
    speed: float = 1.0


class OnScreenController:
    """Manages mpv-style auto-hiding floating HUD overlays on video frames."""

    IDLE_TIMEOUT_SECONDS: float = 2.5

    def __init__(self, idle_timeout: float = IDLE_TIMEOUT_SECONDS) -> None:
        self.idle_timeout = idle_timeout
        self._last_interaction_time: float = time.perf_counter()
        self.is_visible: bool = True

    def trigger_interaction(self) -> None:
        """Called whenever a mouse movement, click, or key press occurs."""
        self._last_interaction_time = time.perf_counter()
        self.is_visible = True

    def check_idle(self) -> bool:
        """Updates and returns whether the OSC should remain visible."""
        if time.perf_counter() - self._last_interaction_time > self.idle_timeout:
            self.is_visible = False
        return self.is_visible

    def render_overlay(self, frame_img: Image.Image, state: OSCState) -> Image.Image:
        """
        Renders mpv-style top title bar and floating bottom control pill on the frame.
        Returns a new PIL Image with the translucent overlay applied.
        """
        if not self.check_idle():
            return frame_img

        img = frame_img.copy()
        w, h = img.size
        if w < 40 or h < 40:
            return img

        # Create overlay layer for translucent glassmorphism
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Compute dynamic font sizing
        font_size = max(11, min(24, int(h * 0.035)))
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont
        bold_font: ImageFont.FreeTypeFont | ImageFont.ImageFont
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
            bold_font = ImageFont.truetype("arialbd.ttf", font_size)
        except Exception:
            try:
                font = ImageFont.load_default(size=font_size)
                bold_font = font
            except TypeError:
                font = ImageFont.load_default()
                bold_font = font

        # ----------------------------------------------------
        # 1. Top Title Bar (Glassmorphic dark band)
        # ----------------------------------------------------
        top_h = max(24, int(h * 0.08))
        draw.rectangle([0, 0, w, top_h], fill=(12, 16, 24, 180))

        title_text = f"🔱 PINAK │ {state.title}"
        right_info = f"[{state.quality_label} | {state.renderer_mode}]"
        draw.text(
            (12, (top_h - font_size) // 2), title_text, font=bold_font, fill=(120, 225, 255, 240)
        )
        # Draw right info
        try:
            r_bbox = draw.textbbox((0, 0), right_info, font=font)
            r_w = r_bbox[2] - r_bbox[0]
            draw.text(
                (w - r_w - 14, (top_h - font_size) // 2),
                right_info,
                font=font,
                fill=(200, 220, 240, 200),
            )
        except Exception:
            pass

        # ----------------------------------------------------
        # 2. Bottom Floating Control Pill
        # ----------------------------------------------------
        pill_w = max(200, int(w * 0.88))
        pill_h = max(36, int(h * 0.12))
        pill_x1 = (w - pill_w) // 2
        pill_y1 = h - pill_h - max(12, int(h * 0.04))
        pill_x2 = pill_x1 + pill_w
        pill_y2 = pill_y1 + pill_h

        # Translucent rounded glass pill
        draw.rounded_rectangle(
            [pill_x1, pill_y1, pill_x2, pill_y2],
            radius=10,
            fill=(14, 18, 28, 210),
            outline=(50, 70, 100, 200),
            width=1,
        )

        # Progress timeline bar inside pill
        prog_margin_x = 18
        bar_x1 = pill_x1 + prog_margin_x
        bar_x2 = pill_x2 - prog_margin_x
        bar_y1 = pill_y1 + int(pill_h * 0.28)
        bar_y2 = bar_y1 + max(4, int(pill_h * 0.12))

        # Background track (dark charcoal)
        draw.rounded_rectangle([bar_x1, bar_y1, bar_x2, bar_y2], radius=3, fill=(45, 55, 75, 220))

        # Filled progress track (vibrant cyan/emerald gradient)
        frac = min(1.0, max(0.0, state.current_pts / max(0.001, state.duration_sec)))
        filled_w = int((bar_x2 - bar_x1) * frac)
        if filled_w > 0:
            draw.rounded_rectangle(
                [bar_x1, bar_y1, bar_x1 + filled_w, bar_y2], radius=3, fill=(40, 200, 240, 240)
            )
            # Scrubber thumb handle
            thumb_r = max(4, int(pill_h * 0.14))
            thumb_cx = bar_x1 + filled_w
            thumb_cy = (bar_y1 + bar_y2) // 2
            draw.ellipse(
                [thumb_cx - thumb_r, thumb_cy - thumb_r, thumb_cx + thumb_r, thumb_cy + thumb_r],
                fill=(255, 255, 255, 255),
            )

        # Labels below progress bar
        status_icon = "▶" if state.is_playing else "❚❚"
        time_str = (
            f"{self._format_time(state.current_pts)} / {self._format_time(state.duration_sec)}"
        )
        vol_str = "🔇 MUTED" if state.is_muted else f"🔊 {int(state.volume * 100)}%"
        sub_str = f"CC: {state.subtitle_track_name.upper()}"

        label_y = bar_y2 + 4
        draw.text(
            (bar_x1, label_y),
            f"{status_icon}  {time_str}",
            font=bold_font,
            fill=(240, 245, 255, 230),
        )
        draw.text(
            (bar_x1 + int((bar_x2 - bar_x1) * 0.55), label_y),
            vol_str,
            font=font,
            fill=(200, 215, 235, 200),
        )
        draw.text(
            (bar_x1 + int((bar_x2 - bar_x1) * 0.80), label_y),
            sub_str,
            font=font,
            fill=(130, 220, 160, 220),
        )

        # Composite overlay onto base frame
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        return Image.alpha_composite(img, overlay).convert("RGB")

    @classmethod
    def _format_time(cls, seconds: float) -> str:
        s = max(0, int(seconds))
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
