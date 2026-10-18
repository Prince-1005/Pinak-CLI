"""Unit tests for pinak.media.picture modules."""

from pathlib import Path

import pytest
from PIL import Image

from pinak.media.core.input_parser import KeyEvent
from pinak.media.picture.viewer import PictureViewer


@pytest.fixture
def sample_images(tmp_path: Path):
    p1 = tmp_path / "img1.png"
    p2 = tmp_path / "img2.png"
    Image.new("RGB", (100, 50), color=(255, 0, 0)).save(p1)
    Image.new("RGB", (100, 50), color=(0, 255, 0)).save(p2)
    return [p1, p2]


def test_picture_viewer_navigation_and_zoom(sample_images):
    viewer = PictureViewer(sample_images)
    assert viewer.current_index == 0
    assert viewer.zoom == 1.0

    # Zoom in
    viewer.handle_input(KeyEvent(key="+"))
    assert viewer.zoom == 1.25

    # Zoom out
    viewer.handle_input(KeyEvent(key="-"))
    assert viewer.zoom == 1.0

    # Pan
    viewer.handle_input(KeyEvent(key="right"))
    assert viewer.pan_x == 25
    viewer.handle_input(KeyEvent(key="down"))
    assert viewer.pan_y == 25

    # Reset
    viewer.handle_input(KeyEvent(key="0"))
    assert viewer.zoom == 1.0
    assert viewer.pan_x == 0.0
    assert viewer.pan_y == 0.0

    # Rotation
    viewer.handle_input(KeyEvent(key="r"))
    assert viewer.rotation_deg == 90

    # Next / Prev
    viewer.handle_input(KeyEvent(key="n"))
    assert viewer.current_index == 1
    viewer.handle_input(KeyEvent(key="p"))
    assert viewer.current_index == 0

    # Circular wrap: at first picture (0), 'p' wraps to last picture (1)
    viewer.handle_input(KeyEvent(key="p"))
    assert viewer.current_index == 1

    # Circular wrap: at last picture (1), 'n' wraps to first picture (0)
    viewer.handle_input(KeyEvent(key="n"))
    assert viewer.current_index == 0


def test_picture_viewer_render_tui(sample_images):
    viewer = PictureViewer(sample_images)
    tui_output = viewer.render_tui(cols=80, rows=24, elapsed_sec=0.0)

    assert "PINAK VIEWER" in tui_output
    assert "Close Media" in tui_output
    assert "img1.png" in tui_output


def test_picture_viewer_mixed_files_and_corrupt_fallback(tmp_path: Path):
    """Verifies that non-images are filtered and corrupted images load placeholder safely."""
    p1 = tmp_path / "valid1.png"
    p2 = tmp_path / "valid2.jpg"
    audio_file = tmp_path / "sound.mp3"
    corrupt_file = tmp_path / "broken.png"

    Image.new("RGB", (20, 20), color=(10, 20, 30)).save(p1)
    Image.new("RGB", (20, 20), color=(40, 50, 60)).save(p2)
    audio_file.write_bytes(b"ID3FakeAudioData")
    corrupt_file.write_bytes(b"NotARealPngFileAtAll")

    # Pass mixed playlist
    viewer = PictureViewer([p1, audio_file, corrupt_file, p2], initial_index=0)
    # audio_file should have been filtered out
    assert audio_file not in viewer.image_paths
    assert len(viewer.image_paths) == 3

    # Navigate to corrupt_file: must not raise exception, but load placeholder
    viewer.next_image()
    assert viewer._current_loaded is not None
    assert viewer._current_loaded.width > 0

    # Continue navigation: wraps circularly without crash
    viewer.next_image()
    assert viewer.current_index == 2
    viewer.next_image()
    assert viewer.current_index == 0


def test_sibling_seeder_media_type_isolation(tmp_path: Path):
    """Verifies that SiblingPlaylistSeeder isolates siblings by media category."""
    from pinak.media.picker.sibling_seeder import SiblingPlaylistSeeder

    p1 = tmp_path / "a.jpg"
    p2 = tmp_path / "b.png"
    s1 = tmp_path / "c.mp3"
    v1 = tmp_path / "d.mp4"

    p1.write_bytes(b"dummy")
    p2.write_bytes(b"dummy")
    s1.write_bytes(b"dummy")
    v1.write_bytes(b"dummy")

    # Seeding from picture -> only pictures
    pic_siblings, pic_idx = SiblingPlaylistSeeder.seed_from_file(p1)
    assert len(pic_siblings) == 2
    assert p1 in pic_siblings and p2 in pic_siblings
    assert s1 not in pic_siblings and v1 not in pic_siblings
    assert pic_idx == 0

    # Seeding from audio -> only audio
    aud_siblings, aud_idx = SiblingPlaylistSeeder.seed_from_file(s1)
    assert len(aud_siblings) == 1
    assert aud_siblings[0] == s1
    assert aud_idx == 0

    # Seeding from video -> only video
    vid_siblings, vid_idx = SiblingPlaylistSeeder.seed_from_file(v1)
    assert len(vid_siblings) == 1
    assert vid_siblings[0] == v1
    assert vid_idx == 0


def test_picture_viewer_uses_zoom_and_arrow_only_pan(sample_images):
    """Picture controls expose zoom and arrow panning without 1:1 or letter panning."""
    viewer = PictureViewer(sample_images)
    output = viewer.render_tui(cols=100, rows=24, elapsed_sec=0.0)
    assert "Original: 100x50 px" in output
    assert "[Arrows] Pan" in output
    assert "1:1" not in output
    assert "WASD" not in output

    for key in ("up", "down", "left", "right"):
        assert viewer.handle_input(KeyEvent(key=key)) is True
    assert viewer.pan_x == viewer.pan_y == 0
    for key in ("w", "a", "s", "d", "h", "j", "k", "l", "1", "z"):
        assert viewer.handle_input(KeyEvent(key=key)) is False
    assert viewer.pan_x == viewer.pan_y == 0

    assert viewer.handle_input(KeyEvent(key="+")) is True
    assert "125%" in viewer.render_tui(cols=100, rows=24, elapsed_sec=0.0)


def test_picture_viewer_gpu_display_image(sample_images):
    """Verifies that get_current_display_image supplies full-res rotated frames to GPU window."""
    viewer = PictureViewer(sample_images)
    img = viewer.get_current_display_image()
    assert img is not None
    assert img.size == (100, 50)

    # Rotate 90 degrees
    viewer.handle_input(KeyEvent(key="r"))
    rot_img = viewer.get_current_display_image()
    assert rot_img is not None
    assert rot_img.size == (50, 100)


def test_picture_viewer_defaults_to_quadrant_renderer(sample_images):
    """Verifies that PictureViewer defaults to high-density QuadrantRenderer with 2x2 sub-pixels."""
    viewer = PictureViewer(sample_images)
    assert viewer.renderer.mode_name == "quadrant"
    tui_output = viewer.render_tui(cols=80, rows=24, elapsed_sec=0.0)
    assert "QUADRANT (2x2 Quad)" in tui_output
    assert "100x50" in tui_output


def test_quadrant_renderer_exact_1to1_execution():
    """Verifies QuadrantRenderer handles both fit and exact_1to1 modes without error."""
    from pinak.media.renderers.quadrant import QuadrantRenderer

    img = Image.new("RGB", (60, 40), color=(120, 200, 255))
    renderer = QuadrantRenderer()

    # Fit mode
    out_fit = renderer.render_frame(img, target_cols=40, target_rows=20, exact_1to1=False)
    assert isinstance(out_fit, str)
    assert len(out_fit) > 0

    # 1:1 exact native pixel mode
    out_1to1 = renderer.render_frame(img, target_cols=40, target_rows=20, exact_1to1=True)
    assert isinstance(out_1to1, str)
    assert len(out_1to1) > 0


def test_fallback_manager_media_type_picture_elevation():
    """Verifies that FallbackManager returns QuadrantRenderer for pictures on TrueColor terminals."""
    from pinak.media.core.terminal_caps import TerminalCapabilities
    from pinak.media.sync.fallback_manager import FallbackManager

    caps = TerminalCapabilities(has_truecolor=True)
    pic_renderer = FallbackManager.get_best_renderer(caps, media_type="picture")
    assert pic_renderer.mode_name == "quadrant"

    vid_renderer = FallbackManager.get_best_renderer(caps, media_type="video")
    assert vid_renderer.mode_name == "halfblock"


def test_picture_viewer_rotate_ccw_and_removed_slideshow_exif(sample_images):
    """Verifies that PictureViewer binds rotate_ccw/rotate_cw and has removed slideshow and EXIF."""
    viewer = PictureViewer(sample_images)
    assert viewer.rotation_deg == 0
    assert not hasattr(viewer, "slideshow_active")

    # Rotate CCW with Shift+R / R
    viewer.handle_input(KeyEvent(key="R", shift=True))
    assert viewer.rotation_deg == 270

    # Rotate CW with r
    viewer.handle_input(KeyEvent(key="r"))
    assert viewer.rotation_deg == 0

    # Space, t, and i should not trigger slideshow or exif
    assert viewer.handle_input(KeyEvent(key="space")) is False
    assert viewer.handle_input(KeyEvent(key="t")) is False
    assert viewer.handle_input(KeyEvent(key="i")) is False

    # Responsive headers and footers must NOT display Slideshow or EXIF
    for w in (130, 85, 70, 50):
        tui = viewer.render_tui(cols=w, rows=24, elapsed_sec=0.0)
        assert "Slideshow" not in tui
        assert "EXIF" not in tui
        assert "[i]" not in tui


def test_picture_viewer_zoom_preset_removed(sample_images):
    """Verifies that [q] Zoom Preset feature is removed from photo viewer."""
    viewer = PictureViewer(sample_images)
    initial_zoom = viewer.zoom

    # Pressing 'q' should NOT trigger zoom preset or change zoom
    handled = viewer.handle_input(KeyEvent(key="q"))
    assert handled is False
    assert viewer.zoom == initial_zoom

    # Responsive footers across screen widths must NOT display Zoom Preset
    for w in (130, 85, 70, 50):
        tui = viewer.render_tui(cols=w, rows=24, elapsed_sec=0.0)
        assert "Zoom Preset" not in tui
        assert "[q] Zoom" not in tui
        assert "[q]" not in tui
