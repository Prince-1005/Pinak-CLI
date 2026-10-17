"""Unit tests for ColorQuantizer and spatial dithering algorithms."""

from PIL import Image

from pinak.media.renderers.dither import ColorQuantizer
from pinak.media.renderers.halfblock import HalfBlockRenderer


def test_floyd_steinberg_dithering():
    # Create test gradient image
    img = Image.new("RGB", (64, 64))
    pixels = img.load()
    for y in range(64):
        for x in range(64):
            pixels[x, y] = (int(x * 3.5), int(y * 3.5), int((x + y) * 1.75))

    dithered = ColorQuantizer.floyd_steinberg_dither(img, levels_per_channel=8)
    assert dithered.size == (64, 64)
    assert dithered.mode == "RGB"
    # Ensure dithering produced non-uniform neighboring pixel variations
    p1 = dithered.getpixel((10, 10))
    p2 = dithered.getpixel((11, 10))
    assert isinstance(p1, tuple) and len(p1) == 3
    assert isinstance(p2, tuple) and len(p2) == 3


def test_ordered_bayer_dithering():
    img = Image.new("RGB", (32, 32), color=(128, 128, 128))
    bayered = ColorQuantizer.ordered_bayer_dither(img, spread=16.0)
    assert bayered.size == (32, 32)
    # Due to Bayer matrix, different positions have different threshold modifications
    assert bayered.getpixel((0, 0)) != bayered.getpixel((1, 0))


def test_halfblock_renderer_dither_integration():
    img = Image.new("RGB", (40, 40), color=(100, 150, 200))
    r_none = HalfBlockRenderer(dither_mode="none")
    r_bayer = HalfBlockRenderer(dither_mode="bayer")
    r_fs = HalfBlockRenderer(dither_mode="fs")

    frame_none = r_none.render_frame(img, 20, 10)
    frame_bayer = r_bayer.render_frame(img, 20, 10)
    frame_fs = r_fs.render_frame(img, 20, 10)

    assert "▀" in frame_none
    assert "▀" in frame_bayer
    assert "▀" in frame_fs
