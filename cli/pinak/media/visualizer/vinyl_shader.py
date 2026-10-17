"""Procedural vinyl LP record shader with concentric micro-grooves and anisotropic specular sheen."""

from __future__ import annotations

import math

from PIL import Image, ImageDraw


class ProceduralVinylShader:
    """Renders a procedural vintage black vinyl LP record with physical reflections."""

    def __init__(self, diameter: int = 240, label_ratio: float = 0.38) -> None:
        self.diameter = max(64, diameter)
        self.radius = self.diameter // 2
        self.label_radius = int(self.radius * label_ratio)
        self._cached_base_vinyl: Image.Image = self._generate_base_vinyl()

    def _generate_base_vinyl(self) -> Image.Image:
        """Generates the static body, outer rim, and concentric sound micro-grooves."""
        img = Image.new("RGBA", (self.diameter, self.diameter), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cx, cy = self.radius, self.radius

        # 1. Base dark obsidian vinyl platter
        draw.ellipse((0, 0, self.diameter, self.diameter), fill=(20, 20, 20, 255))

        # 2. Outer run-in rim
        draw.ellipse(
            (2, 2, self.diameter - 2, self.diameter - 2), outline=(45, 45, 45, 255), width=2
        )

        # 3. Procedural concentric grooves between label and rim
        for r in range(self.label_radius + 4, self.radius - 4, 3):
            # Alternating groove contrast
            gray_val = 18 + int(8 * math.sin(r * 0.75))
            draw.ellipse(
                (cx - r, cy - r, cx + r, cy + r),
                outline=(gray_val, gray_val, gray_val, 255),
                width=1,
            )

        # 4. Run-out groove near label
        draw.ellipse(
            (
                cx - self.label_radius - 2,
                cy - self.label_radius - 2,
                cx + self.label_radius + 2,
                cy + self.label_radius + 2,
            ),
            outline=(35, 35, 35, 255),
            width=2,
        )

        return img

    def render_vinyl(self, angle_deg: float) -> Image.Image:
        """Composites the vinyl platter with dynamic rotating specular sheen highlights."""
        frame = self._cached_base_vinyl.copy()
        draw = ImageDraw.Draw(frame, "RGBA")
        cx, cy = self.radius, self.radius

        # Render 2 opposing anisotropic specular light wedges
        rad_angle = math.radians(angle_deg)
        for offset in (0, math.pi):
            wedge_dir = rad_angle + offset
            # Draw semi-transparent light arcs across the grooves
            p1_x = cx + int((self.radius - 8) * math.cos(wedge_dir - 0.25))
            p1_y = cy + int((self.radius - 8) * math.sin(wedge_dir - 0.25))
            p2_x = cx + int((self.radius - 8) * math.cos(wedge_dir + 0.25))
            p2_y = cy + int((self.radius - 8) * math.sin(wedge_dir + 0.25))

            draw.polygon([(cx, cy), (p1_x, p1_y), (p2_x, p2_y)], fill=(255, 255, 255, 18))

        return frame
