"""Vintage Gramophone Turntable simulation with rotational physics and tone-arm tracking."""

from __future__ import annotations

import math

from PIL import Image, ImageDraw

from .cover_art import CoverArtRotator
from .vinyl_shader import ProceduralVinylShader


class GramophoneTurntable:
    """Simulates a vintage gramophone turntable spinning at 33⅓ RPM with tone-arm needle tracking."""

    TARGET_RPM = 33.333
    TARGET_OMEGA = (TARGET_RPM * 360.0) / 60.0  # ~200.0 degrees / second

    def __init__(
        self,
        diameter: int = 200,
        artwork_bytes: bytes | None = None,
    ) -> None:
        self.diameter = max(80, diameter)
        self.radius = self.diameter // 2
        label_diam = int(self.diameter * 0.38)

        self.vinyl_shader = ProceduralVinylShader(diameter=self.diameter, label_ratio=0.38)
        self.art_rotator = CoverArtRotator(artwork_source=artwork_bytes, label_diameter=label_diam)

        self.current_angle: float = 0.0
        self.current_omega: float = self.TARGET_OMEGA
        self.is_spinning: bool = True
        self.is_parked: bool = False

    def set_parked(self, parked: bool) -> None:
        """Sets whether the tone-arm is lifted and returned to the rest cradle."""
        self.is_parked = parked

    def update_physics(self, dt: float, is_playing: bool) -> None:
        """Updates rotational velocity with inertia damping and increments angle."""
        target_omega = self.TARGET_OMEGA if (is_playing and not self.is_parked) else 0.0
        # Exponential smoothing (tau = 0.25 sec)
        alpha = 1.0 - math.exp(-max(0.001, dt) / 0.25)
        self.current_omega += (target_omega - self.current_omega) * alpha

        self.current_angle = (self.current_angle + self.current_omega * dt) % 360.0
        self.is_spinning = abs(self.current_omega) > 0.5

    def render_turntable(self, progress_frac: float = 0.0) -> Image.Image:
        """Composites vinyl record, spinning label, and tone-arm."""
        # 1. Base vinyl record with anisotropic light sheen
        canvas = self.vinyl_shader.render_vinyl(self.current_angle)

        # 2. Rotating circular album art
        rot_label = self.art_rotator.rotate(self.current_angle)
        label_offset = (self.diameter - rot_label.width) // 2
        canvas.paste(rot_label, (label_offset, label_offset), rot_label)

        # 3. Center metal spindle
        draw = ImageDraw.Draw(canvas)
        cx, cy = self.radius, self.radius
        spindle_r = max(2, int(self.radius * 0.04))
        draw.ellipse(
            (cx - spindle_r, cy - spindle_r, cx + spindle_r, cy + spindle_r),
            fill=(220, 220, 220, 255),
            outline=(100, 100, 100, 255),
            width=1,
        )

        # 4. Tone-arm tracking needle
        self._draw_tone_arm(draw, progress_frac)

        return canvas

    def _draw_tone_arm(self, draw: ImageDraw.ImageDraw, progress_frac: float) -> None:
        """Draws the mechanical tone-arm sweeping inward proportional to progress or parked in cradle."""
        cx, cy = self.radius, self.radius

        # Pivot point in upper-right corner
        pivot_x = int(self.diameter * 0.92)
        pivot_y = int(self.diameter * 0.08)

        # Tone-arm rest cradle
        cradle_x = pivot_x - 4
        cradle_y = pivot_y + int(self.radius * 0.72)
        draw.rectangle(
            (cradle_x - 5, cradle_y - 2, cradle_x + 5, cradle_y + 2),
            fill=(60, 60, 60, 255),
            outline=(160, 160, 160, 255),
        )

        if self.is_parked or progress_frac >= 1.0:
            needle_x = cradle_x
            needle_y = cradle_y
        else:
            frac = max(0.0, min(1.0, progress_frac))
            # Needle tip moves from outer rim (0.85 radius) to inner label (0.42 radius)
            needle_r = (self.radius * 0.85) - frac * (self.radius * 0.43)
            needle_angle = math.radians(25.0 + frac * 15.0)
            needle_x = cx + int(needle_r * math.cos(needle_angle))
            needle_y = cy + int(needle_r * math.sin(needle_angle))

        # Tone-arm shaft
        draw.line([(pivot_x, pivot_y), (needle_x, needle_y)], fill=(180, 180, 180, 255), width=3)
        # Pivot base
        draw.ellipse(
            (pivot_x - 6, pivot_y - 6, pivot_x + 6, pivot_y + 6),
            fill=(100, 100, 100, 255),
            outline=(220, 220, 220, 255),
        )
        # Headshell / cartridge at needle tip
        cartridge_color = (
            (140, 140, 140, 255)
            if (self.is_parked or progress_frac >= 1.0)
            else (218, 165, 32, 255)
        )
        draw.ellipse((needle_x - 3, needle_y - 3, needle_x + 3, needle_y + 3), fill=cartridge_color)
