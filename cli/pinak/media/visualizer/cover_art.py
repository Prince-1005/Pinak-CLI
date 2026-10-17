"""Circular album cover art extraction, masking, and 2D affine rotation."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw


class CoverArtRotator:
    """Masks rectangular cover art to an inner record label with spindle hole and rotates in 2D."""

    def __init__(
        self,
        artwork_source: bytes | Image.Image | None = None,
        label_diameter: int = 120,
    ) -> None:
        self.label_diameter = max(32, label_diameter)
        self.spindle_radius = max(3, int(self.label_diameter * 0.08))
        self.label_radius = self.label_diameter // 2
        self._base_label: Image.Image = self._prepare_label(artwork_source)

    def _prepare_label(self, source: bytes | Image.Image | None) -> Image.Image:
        """Prepares circular album art label with central spindle hole."""
        size = (self.label_diameter, self.label_diameter)

        if source is not None:
            try:
                if isinstance(source, bytes):
                    raw_img = Image.open(io.BytesIO(source)).convert("RGBA")
                else:
                    raw_img = source.convert("RGBA")
                img = raw_img.resize(size, Image.Resampling.BILINEAR)
            except Exception:
                img = self._create_default_label(size)
        else:
            img = self._create_default_label(size)

        # Create circular alpha mask with spindle hole
        mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        cx, cy = self.label_radius, self.label_radius

        # Outer circle of label
        draw.ellipse((0, 0, self.label_diameter, self.label_diameter), fill=255)
        # Spindle cutout
        draw.ellipse(
            (
                cx - self.spindle_radius,
                cy - self.spindle_radius,
                cx + self.spindle_radius,
                cy + self.spindle_radius,
            ),
            fill=0,
        )

        img.putalpha(mask)
        return img

    def _create_default_label(self, size: tuple[int, int]) -> Image.Image:
        """Generates vintage crimson record label when no artwork is embedded."""
        img = Image.new("RGBA", size, (139, 30, 30, 255))  # Deep crimson
        draw = ImageDraw.Draw(img)
        cx, cy = size[0] // 2, size[1] // 2

        # Gold decorative ring
        ring_r = int(self.label_radius * 0.85)
        draw.ellipse(
            (cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r),
            outline=(218, 165, 32, 255),
            width=2,
        )
        return img

    def rotate(self, angle_deg: float) -> Image.Image:
        """Rotates the circular label by angle_deg."""
        # Negative angle for authentic clockwise rotation
        return self._base_label.rotate(-angle_deg, resample=Image.Resampling.BILINEAR)
