"""Unit tests for pinak.media.renderers modules."""

from PIL import Image

from pinak.media.renderers.ascii_retro import ASCIIRenderer
from pinak.media.renderers.halfblock import HalfBlockRenderer
from pinak.media.renderers.pixel_iterm2 import ITerm2Renderer
from pinak.media.renderers.pixel_kitty import KittyRenderer
from pinak.media.renderers.pixel_sixel import SixelRenderer
from pinak.media.renderers.scaler import ViewportScaler


def test_viewport_scaler():
    # 200x100 image into 80x24 terminal in half-block mode
    vp_hb = ViewportScaler.calculate_halfblock_viewport(200, 100, cols=80, rows=24)
    assert vp_hb.width <= 80
    assert vp_hb.height <= 48
    assert vp_hb.height % 2 == 0

    # ASCII mode
    vp_asc = ViewportScaler.calculate_ascii_viewport(200, 100, cols=80, rows=24)
    assert vp_asc.width <= 80
    assert vp_asc.height <= 24


def test_halfblock_renderer():
    img = Image.new("RGB", (20, 10), color=(255, 0, 0))
    renderer = HalfBlockRenderer()
    out = renderer.render_frame(img, target_cols=40, target_rows=10)

    assert "▀" in out
    assert "\x1b[38;2;255;0;0m" in out
    assert renderer.mode_name == "halfblock"
    assert renderer.is_pixel_native is False


def test_ascii_renderer():
    img = Image.new("RGB", (20, 10), color=(128, 128, 128))
    renderer = ASCIIRenderer(color_profile="green")
    out = renderer.render_frame(img, target_cols=40, target_rows=10)

    assert renderer.mode_name == "ascii"
    assert "\x1b[38;2;0;255;70m" in out


def test_kitty_renderer():
    img = Image.new("RGB", (20, 10), color=(0, 0, 255))
    renderer = KittyRenderer()

    # Native APC test
    out_native = renderer.render_native_kitty(img, target_cols=40, target_rows=10)
    assert renderer.mode_name == "kitty"
    assert renderer.is_pixel_native is True
    assert "\x1b_Ga=T" in out_native
    assert out_native.split("\x1b[2K")[0].strip("\n").endswith("\x1b\\")

    # Braille micro-matrix fallback test
    out_braille = renderer.render_braille(img, target_cols=40, target_rows=10)
    assert len(out_braille.splitlines()) == 10
    assert "\x1b[2K" in out_braille

    # Unified render_frame with force_native
    out_forced = renderer.render_frame(img, target_cols=40, target_rows=10, force_native=True)
    assert "\x1b_Ga=T" in out_forced


def test_sixel_renderer():
    img = Image.new("RGB", (20, 10), color=(0, 255, 0))
    renderer = SixelRenderer()
    out = renderer.render_frame(img, target_cols=40, target_rows=10)

    assert renderer.mode_name == "sixel"
    assert renderer.is_pixel_native is True
    assert out.startswith("\x1bPq")
    assert out.endswith("\x1b\\")


def test_sixel_renderer_custom_cell_metrics():
    """Verifies that SixelRenderer accepts custom font cell metrics and scales pixels accordingly (FALLBACK-06)."""
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    # Custom cell metrics: 12x24 instead of default 10x20
    renderer = SixelRenderer(cell_width_px=12, cell_height_px=24)
    assert renderer.cell_width_px == 12
    assert renderer.cell_height_px == 24
    out = renderer.render_frame(img, target_cols=20, target_rows=10)
    assert out.startswith("\x1bPq")
    assert out.endswith("\x1b\\")


def test_iterm2_renderer():
    img = Image.new("RGB", (20, 10), color=(255, 255, 0))
    renderer = ITerm2Renderer()
    out = renderer.render_frame(img, target_cols=40, target_rows=10)

    assert renderer.mode_name == "iterm2"
    assert renderer.is_pixel_native is True
    assert out.startswith("\x1b]1337;File=inline=1;")
    assert out.endswith("\x07")


def test_kitty_braille_aspect_ratio_preservation():
    """Verifies that 2x4 Braille micro-matrix preserves original aspect ratio and shape without vertical stretching."""
    from pinak.media.renderers.pixel_kitty import KittyRenderer
    from pinak.media.renderers.scaler import ViewportScaler

    # 1. Test ViewportScaler calculation for a 16:9 widescreen image (1920x1080) in 80x40 terminal
    vp = ViewportScaler.calculate_braille_viewport(1920, 1080, cols=80, rows=40, cell_ratio=2.0)
    assert vp.width <= 160
    assert vp.height <= 160
    assert vp.width % 2 == 0
    assert vp.height % 4 == 0

    # With cell_ratio=2.0, Braille dots are 1:1 square. The rendered dot aspect ratio must closely match 1920/1080 (~1.777)
    rendered_aspect = vp.width / vp.height
    assert abs(rendered_aspect - (1920.0 / 1080.0)) < 0.1
    # Check that vertical letterbox padding is applied so the photo is not vertically stretched
    assert vp.pad_top > 0

    # 2. Test actual render_braille output produces correct number of terminal rows and valid Unicode Braille
    r = KittyRenderer()
    img = Image.new("RGB", (640, 360), color=(50, 120, 200))
    out = r.render_braille(img, target_cols=60, target_rows=25)
    lines = out.splitlines()
    assert len(lines) == 25
    # Contains 24-bit ANSI TrueColor and Braille character (U+2800..U+28FF)
    assert any("⠀" <= ch <= "⣿" for ch in out)
    assert "\x1b[2K" in out


def test_renderers_actual_size_no_window_stretch():
    """Verifies that media smaller than terminal canvas renders at actual size with centering padding rather than stretching over window."""
    from pinak.media.renderers.quadrant import QuadrantRenderer

    small_img = Image.new("RGB", (30, 20), color=(255, 100, 50))
    target_cols = 80
    target_rows = 24

    # 1. HalfBlock: 30x20 image on 80x24 terminal should render 30 cols x 10 rows centered
    hb = HalfBlockRenderer()
    hb_out = hb.render_frame(small_img, target_cols=target_cols, target_rows=target_rows)
    hb_lines = hb_out.splitlines()
    assert len(hb_lines) == target_rows
    # Top and bottom padding rows must exist (empty spaces)
    assert hb_lines[0].strip() == ""
    assert hb_lines[-1].strip() == ""

    # 2. Quadrant: 30x20 image must not upscale to 80x24
    quad = QuadrantRenderer()
    quad_out = quad.render_frame(small_img, target_cols=target_cols, target_rows=target_rows)
    quad_lines = quad_out.splitlines()
    assert len(quad_lines) == target_rows
    assert quad_lines[0].strip() == ""
    assert quad_lines[-1].strip() == ""

    # 3. Braille
    kitty = KittyRenderer()
    br_out = kitty.render_braille(small_img, target_cols=target_cols, target_rows=target_rows)
    br_lines = br_out.splitlines()
    assert len(br_lines) == target_rows
    assert br_lines[0].replace("\x1b[2K", "").strip() == ""
    assert br_lines[-1].replace("\x1b[2K", "").strip() == ""

    # 4. ASCII
    asc = ASCIIRenderer()
    asc_out = asc.render_frame(small_img, target_cols=target_cols, target_rows=target_rows)
    asc_lines = asc_out.splitlines()
    assert len(asc_lines) == target_rows
    assert asc_lines[0].strip() == ""
    assert asc_lines[-1].strip() == ""


def test_renderers_aspect_ratio_preservation_no_cropping():
    """Verifies that large square images are not cropped into full-window rectangles but preserve their true shape."""
    from pinak.media.renderers.quadrant import QuadrantRenderer
    from pinak.media.renderers.scaler import ViewportScaler

    # Square image (600x600) into 100 cols x 30 rows terminal
    vp = ViewportScaler.calculate_halfblock_viewport(
        600, 600, cols=100, rows=30, allow_upscale=False
    )
    # Virtual canvas is 100 cols x 60 rows. Scaled square should be 60x60 virtual pixels
    assert vp.width == 60
    assert vp.height == 60
    # Left padding must center the square: (100 - 60) // 2 = 20
    assert vp.pad_left == 20
    assert vp.pad_top == 0

    # Quadrant renderer on square image
    sq_img = Image.new("RGB", (400, 400), color=(0, 200, 100))
    renderer = QuadrantRenderer()
    out = renderer.render_frame(sq_img, target_cols=80, target_rows=25)
    lines = out.splitlines()
    assert len(lines) == 25
    # Scaled quadrant viewport must preserve square shape with pillarbox padding (not stretched across 80 cols)
    vp_q = ViewportScaler.calculate_quadrant_viewport(
        400, 400, cols=80, rows=25, allow_upscale=False
    )
    assert vp_q.pad_left == 15
    assert vp_q.width // 2 == 50
    assert vp_q.height // 2 == 25
    # Physical aspect ratio on 1:2 cell terminal is 1:1 square
    assert (vp_q.width // 2) * 10 == (vp_q.height // 2) * 20


def test_quality_profile_manager_native_actual_size():
    """Verifies that QualityProfileManager defaults to native actual size and preserves video aspect ratio."""
    from pinak.media.player.quality import QualityProfileManager

    qm = QualityProfileManager()
    assert qm.current_profile.id == "native"
    assert "Actual Size" in qm.current_profile.label

    # Small video 320x180 in 80x24 terminal (canvas 80x48 virtual px)
    # 320x180 is larger than 80x48, so it scales down preserving 16:9 aspect ratio
    w, h = qm.get_target_dimensions(80, 24, native_w=320, native_h=180)
    assert w <= 80
    assert h <= 48
    # Aspect ratio should closely match 16:9 (~1.777)
    assert abs((w / h) - (320.0 / 180.0)) < 0.2

    # Very small video 40x20 in 80x24 terminal (canvas 80x48 virtual px)
    # Fits within canvas -> renders in its OWN ACTUAL SIZE without upscaling
    w_small, h_small = qm.get_target_dimensions(80, 24, native_w=40, native_h=20)
    assert w_small == 40
    assert h_small == 20


def test_base_renderer_render_braille_fallback():
    """Verifies that BaseRenderer provides a concrete render_braille default falling back to render_frame (BUG-02)."""
    from pinak.media.renderers.base import BaseRenderer

    class CustomRenderer(BaseRenderer):
        @property
        def mode_name(self) -> str:
            return "custom"

        @property
        def is_pixel_native(self) -> bool:
            return False

        def render_frame(self, img, target_cols, target_rows, exact_1to1=False) -> str:
            return f"rendered:{target_cols}x{target_rows}"

    r = CustomRenderer()
    img = Image.new("RGB", (20, 10))
    res = r.render_braille(img, target_cols=40, target_rows=12)
    assert res == "rendered:40x12"


def test_fallback_manager_degrade_renderer_ladder():
    """Verifies FallbackManager graceful degradation ladder across graphics modes (FALLBACK-03)."""
    from pinak.media.sync.fallback_manager import FallbackManager

    # Kitty -> HalfBlock
    kitty = KittyRenderer()
    d1 = FallbackManager.degrade_renderer(kitty)
    assert d1.mode_name == "halfblock"

    # HalfBlock -> ASCII
    d2 = FallbackManager.degrade_renderer(d1)
    assert d2.mode_name == "ascii"

    # ASCII -> ASCII (short ramp)
    d3 = FallbackManager.degrade_renderer(d2)
    assert d3.mode_name == "ascii"


def test_renderers_non_rgb_images():
    """Verifies that non-RGB images (Grayscale 'L', 'RGBA', Palette 'P') do not raise unpacking TypeErrors (BUG-04)."""
    from pinak.media.renderers.ascii_retro import ASCIIRenderer
    from pinak.media.renderers.dither import ColorQuantizer
    from pinak.media.renderers.quadrant import QuadrantRenderer

    ascii_r = ASCIIRenderer()
    quad_r = QuadrantRenderer()

    # Test Grayscale 'L', RGBA, and Palette 'P' modes
    modes = ["L", "RGBA", "P"]
    for mode in modes:
        img = Image.new(mode, (20, 10))
        # Retro ASCII should render without unpacking error
        res_ascii = ascii_r.render_frame(img, target_cols=20, target_rows=10)
        assert isinstance(res_ascii, str)
        assert len(res_ascii) > 0

        # Quadrant renderer should render without error
        res_quad = quad_r.render_frame(img, target_cols=20, target_rows=10)
        assert isinstance(res_quad, str)
        assert len(res_quad) > 0

        # Color quantizer
        dithered = ColorQuantizer.floyd_steinberg_dither(img)
        assert dithered.mode == "RGB"
