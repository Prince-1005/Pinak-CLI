"""Unit tests for QuadrantRenderer and 2x2 Unicode quadrant character packing."""

from __future__ import annotations

from PIL import Image

from pinak.media.renderers.quadrant import QUADRANT_CHARS, QuadrantRenderer
from pinak.media.renderers.scaler import ViewportScaler


def test_quadrant_characters_table():
    """Verifies that QUADRANT_CHARS contains all 16 unique Unicode block elements."""
    assert len(QUADRANT_CHARS) == 16
    assert QUADRANT_CHARS[0] == " "
    assert QUADRANT_CHARS[3] == "\u2584"  # ▄
    assert QUADRANT_CHARS[10] == "\u258c"  # ▌
    assert QUADRANT_CHARS[12] == "\u2580"  # ▀
    assert QUADRANT_CHARS[15] == "\u2588"  # █


def test_quadrant_viewport_scaling():
    """Verifies that ViewportScaler produces even 2x2 dimensions and correct padding."""
    vp = ViewportScaler.calculate_quadrant_viewport(
        src_w=100, src_h=100, cols=80, rows=24, cell_ratio=2.0
    )
    # Both width and height must be even multiples of 2
    assert vp.width % 2 == 0
    assert vp.height % 2 == 0
    assert vp.width <= 160  # cols * 2
    assert vp.height <= 48  # rows * 2
    assert vp.pad_left >= 0
    assert vp.pad_top >= 0


def test_quadrant_renderer_solid_color():
    """Verifies quadrant rendering of a uniform solid color image."""
    img = Image.new("RGB", (20, 20), color=(255, 0, 0))
    renderer = QuadrantRenderer()
    output = renderer.render_frame(img, target_cols=40, target_rows=15)

    assert isinstance(output, str)
    lines = output.split("\n")
    assert len(lines) == 15
    # Should contain red background TrueColor ANSI code
    assert "48;2;255;0;0" in output


def test_quadrant_renderer_diagonal_checker():
    """Verifies that a 2x2 diagonal checker resolves to Unicode diagonal quadrant block."""
    # 2x2 image: TL=white, TR=black, BL=black, BR=white
    img = Image.new("RGB", (2, 2))
    img.putpixel((0, 0), (255, 255, 255))
    img.putpixel((1, 0), (0, 0, 0))
    img.putpixel((0, 1), (0, 0, 0))
    img.putpixel((1, 1), (255, 255, 255))

    renderer = QuadrantRenderer()
    output = renderer.render_frame(img, target_cols=1, target_rows=1)

    # ▚ is \u259a (TL and BR) or ▞ is \u259e (TR and BL)
    assert "\u259a" in output or "\u259e" in output


def test_quadrant_renderer_with_dithering():
    """Verifies that QuadrantRenderer integrates with Bayer and Floyd-Steinberg dither modes."""
    img = Image.new("RGB", (30, 30), color=(128, 128, 128))
    bayer_ren = QuadrantRenderer(dither_mode="bayer")
    fs_ren = QuadrantRenderer(dither_mode="fs")

    out_bayer = bayer_ren.render_frame(img, target_cols=20, target_rows=10)
    out_fs = fs_ren.render_frame(img, target_cols=20, target_rows=10)

    assert len(out_bayer.split("\n")) == 10
    assert len(out_fs.split("\n")) == 10
