"""Mode 1: iTerm2 Inline Image protocol native pixel renderer."""

from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image

from .base import BaseRenderer


class ITerm2Renderer(BaseRenderer):
    """Renders native pixel images via the iTerm2 OSC 1337 protocol."""

    @property
    def mode_name(self) -> str:
        return "iterm2"

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
        bio = BytesIO()
        img.convert("RGB").save(bio, format="JPEG", quality=85)
        jpeg_bytes = bio.getvalue()
        b64 = base64.b64encode(jpeg_bytes).decode("ascii")

        return (
            f"\x1b]1337;File=inline=1;"
            f"width={target_cols};height={target_rows};preserveAspectRatio=1:{b64}\x07"
        )
