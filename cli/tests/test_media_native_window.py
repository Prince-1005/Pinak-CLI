"""Unit tests for NativeVideoWindow output."""

from unittest.mock import MagicMock, patch

from PIL import Image

from pinak.media.osc.controller import OnScreenController, OSCState
from pinak.media.window.native_window import NativeVideoWindow


def test_native_video_window_init():
    win = NativeVideoWindow(title="Test Win")
    assert win.title == "Test Win"
    assert win.is_open is False
    assert win.is_fullscreen is False


def test_native_video_window_mock_lifecycle():
    fake_cv2 = MagicMock()
    fake_cv2.waitKeyEx.return_value = ord("q")

    with patch.object(NativeVideoWindow, "_init_backend"):
        win = NativeVideoWindow(title="Mock Window")
        win._backend = "cv2"
        win._cv2_module = fake_cv2

        opened = win.open()
        assert opened is True
        assert win.is_open is True
        fake_cv2.namedWindow.assert_called_with("Mock Window", fake_cv2.WINDOW_NORMAL)

        # Show frame
        frame = Image.new("RGB", (640, 360), (0, 0, 0))
        state = OSCState(
            title="Clip",
            current_pts=10.0,
            duration_sec=50.0,
            is_playing=True,
            volume=1.0,
            is_muted=False,
            subtitle_track_name="None",
            quality_label="1080p",
            renderer_mode="NATIVE",
        )
        osc = OnScreenController()

        keys = win.show_frame(frame, state=state, osc=osc)
        assert "q" in keys
        fake_cv2.imshow.assert_called()

        # Toggle fullscreen
        win.toggle_fullscreen()
        assert win.is_fullscreen is True
        fake_cv2.setWindowProperty.assert_called()

        # Close
        win.close()
        assert win.is_open is False
        fake_cv2.destroyWindow.assert_called_with("Mock Window")


def test_native_video_window_key_mapping():
    win = NativeVideoWindow()
    assert win._map_key_code(ord("q")) == "q"
    assert win._map_key_code(32) == "space"
    assert win._map_key_code(ord("f")) == "f"
    assert win._map_key_code(ord("m")) == "m"
    assert win._map_key_code(ord("c")) == "c"


def test_title_change_keeps_opencv_window_handle_and_fullscreen():
    fake_cv2 = MagicMock()
    fake_cv2.getWindowProperty.return_value = 1
    fake_cv2.getWindowImageRect.return_value = (0, 0, 16, 16)
    fake_cv2.waitKeyEx.return_value = -1
    with patch.object(NativeVideoWindow, "_init_backend"):
        win = NativeVideoWindow(title="First track")
    win._backend = "cv2"
    win._cv2_module = fake_cv2
    win.is_open = True
    win.is_fullscreen = True
    win.set_title("Second track")
    assert win.title == "Second track" and win.is_fullscreen
    fake_cv2.setWindowTitle.assert_called_once_with("First track", "Second track")
    win.show_frame(Image.new("RGB", (16, 16), "blue"))
    assert fake_cv2.imshow.call_args.args[0] == "First track"
    fake_cv2.namedWindow.assert_not_called()
    fake_cv2.resizeWindow.assert_not_called()
    win.close()
    fake_cv2.destroyWindow.assert_called_once_with("First track")


def test_title_change_keeps_tkinter_root_and_geometry():
    with patch.object(NativeVideoWindow, "_init_backend"):
        win = NativeVideoWindow(title="First track")
    root = MagicMock()
    win._backend = "tkinter"
    win._tk_root = root
    win.is_open = True
    win.is_fullscreen = True
    win.set_title("Second track")
    root.title.assert_called_once_with("Second track")
    root.destroy.assert_not_called()
    root.geometry.assert_not_called()
    root.attributes.assert_not_called()
    assert win._tk_root is root and win.is_fullscreen and win.is_open


def test_native_window_fills_viewport_without_distortion():
    """A smaller decoded frame scales to a viewable window with letterboxing."""
    import numpy as np

    fake_cv2 = MagicMock()
    fake_cv2.waitKey.return_value = 255
    fake_cv2.waitKeyEx.return_value = -1
    fake_cv2.resize.side_effect = lambda arr, size, **_: np.asarray(
        Image.fromarray(arr).resize(size)
    )
    fake_cv2.getWindowImageRect.return_value = (0, 0, 800, 700)
    fake_cv2.getWindowProperty.return_value = 1

    with patch.object(NativeVideoWindow, "_init_backend"):
        win = NativeVideoWindow(title="Actual Size Win", initial_scale=0.5)
        win._backend = "cv2"
        win._cv2_module = fake_cv2

        # 1. Open with actual size
        with patch.object(NativeVideoWindow, "_available_screen_size", return_value=(1920, 1080)):
            win.open(initial_size=(400, 300))
        fake_cv2.resizeWindow.assert_called_with("Actual Size Win", 400, 300)

        # 2. Show 400x300 frame
        img = Image.new("RGB", (400, 300), color=(180, 180, 180))
        win.show_frame(img)

        # The image fills the width, with 50-pixel bars above and below.
        assert fake_cv2.imshow.called
        canvas_arg = fake_cv2.imshow.call_args[0][1]
        assert canvas_arg.shape == (700, 800, 3)
        assert canvas_arg[350, 400, 0] == 180
        assert canvas_arg[25, 400, 0] == 0

        # A later change from tiny TUI frames to native decode cannot shrink it.
        fake_cv2.resizeWindow.reset_mock()
        win.show_frame(Image.new("RGB", (80, 60), color=(180, 180, 180)))
        fake_cv2.resizeWindow.assert_not_called()


def test_video_frame_shrinks_to_smaller_window_without_changing_ratio():
    """The w window downsizes source pixels and letterboxes the remaining space."""
    import numpy as np

    fake_cv2 = MagicMock()
    fake_cv2.waitKeyEx.return_value = -1
    fake_cv2.getWindowProperty.return_value = 1
    fake_cv2.getWindowImageRect.return_value = (0, 0, 320, 200)
    fake_cv2.resize.side_effect = lambda arr, size, **_: np.asarray(
        Image.fromarray(arr).resize(size)
    )

    with patch.object(NativeVideoWindow, "_init_backend"):
        win = NativeVideoWindow(title="Small Video Win", initial_scale=0.5)
        win._backend = "cv2"
        win._cv2_module = fake_cv2
        with patch.object(NativeVideoWindow, "_available_screen_size", return_value=(1920, 1080)):
            assert win.open(initial_size=(640, 360))

        win.show_frame(Image.new("RGB", (640, 360), color=(120, 130, 140)))
        assert fake_cv2.resize.call_args.args[1] == (320, 180)
        canvas = fake_cv2.imshow.call_args.args[1]
        assert canvas.shape == (200, 320, 3)
        assert canvas[100, 160, 0] == 120
        assert canvas[5, 160, 0] == 0
        win.close()


def test_native_window_compact_size():
    """Verifies that large windows are constrained to a compact screen area while keeping aspect ratio."""
    # 1. 1080p media (1920x1080) must scale down into compact box (<= 854x480)
    w_1080, h_1080 = NativeVideoWindow.compute_compact_size(1920, 1080)
    assert w_1080 <= NativeVideoWindow.MAX_COMPACT_WIDTH
    assert h_1080 <= NativeVideoWindow.MAX_COMPACT_HEIGHT
    assert abs((w_1080 / h_1080) - (16.0 / 9.0)) < 0.05

    # 2. 4K media (3840x2160)
    w_4k, h_4k = NativeVideoWindow.compute_compact_size(3840, 2160)
    assert w_4k <= NativeVideoWindow.MAX_COMPACT_WIDTH
    assert h_4k <= NativeVideoWindow.MAX_COMPACT_HEIGHT
    assert abs((w_4k / h_4k) - (16.0 / 9.0)) < 0.05

    # 3. Small media (400x300) should keep its native size
    w_small, h_small = NativeVideoWindow.compute_compact_size(400, 300)
    assert w_small == 400
    assert h_small == 300


def test_native_window_tkinter_fallback_lifecycle():
    """Verifies Tkinter GUI fallback window creation, frame blitting, and events (FALLBACK-02)."""
    fake_tk = MagicMock()
    fake_root = MagicMock()
    fake_canvas = MagicMock()
    fake_tk.Tk.return_value = fake_root
    fake_tk.Canvas.return_value = fake_canvas
    fake_root.winfo_exists.return_value = True
    fake_canvas.winfo_width.return_value = 800
    fake_canvas.winfo_height.return_value = 600

    fake_imagetk = MagicMock()
    fake_photo = MagicMock()
    fake_imagetk.PhotoImage.return_value = fake_photo

    with patch.object(NativeVideoWindow, "_init_backend"):
        win = NativeVideoWindow(title="Tkinter Window")
        win._backend = "tkinter"
        win._tk_module = fake_tk
        win._imagetk_module = fake_imagetk

        # 1. Open
        assert win.open(initial_size=(640, 360)) is True
        assert win.is_open is True
        fake_tk.Tk.assert_called_once()
        fake_root.title.assert_called_with("Tkinter Window")

        # 2. Simulate key press event captured by binding
        class FakeEvent:
            keysym = "space"
            char = " "

        win._tk_pressed_keys.append("space")

        # 3. Show frame
        img = Image.new("RGB", (640, 360), color=(100, 100, 100))
        keys = win.show_frame(img)
        assert "space" in keys
        fake_canvas.delete.assert_called_with("all")
        fake_canvas.create_image.assert_called()

        # 4. Poll events
        win._tk_pressed_keys.append("q")
        polled = win.poll_events()
        assert polled == ["q"]

        # 5. Toggle fullscreen
        win.toggle_fullscreen()
        assert win.is_fullscreen is True
        fake_root.attributes.assert_called_with("-fullscreen", True)

        # 6. Close
        win.close()
        assert win.is_open is False
        fake_root.destroy.assert_called_once()


def test_native_window_tkinter_key_mapping():
    """Verifies Tkinter event mapping to standard Pinak key names."""
    win = NativeVideoWindow()

    class Ev:
        def __init__(self, sym, ch=""):
            self.keysym = sym
            self.char = ch

    assert win._map_tk_key(Ev("Escape")) == "esc"
    assert win._map_tk_key(Ev("space", " ")) == "space"
    assert win._map_tk_key(Ev("f", "f")) == "f"
    assert win._map_tk_key(Ev("m", "m")) == "m"
    assert win._map_tk_key(Ev("Left")) == "left"
    assert win._map_tk_key(Ev("Right")) == "right"
    assert win._map_tk_key(Ev("Up")) == "up"
    assert win._map_tk_key(Ev("Down")) == "down"
    assert win._map_tk_key(Ev("x", "x")) == "x"


def test_native_window_backend_none_fallback():
    """Verifies graceful behavior when no GUI window backend is available."""
    with patch.object(NativeVideoWindow, "_init_backend"):
        win = NativeVideoWindow()
        win._backend = "none"
        assert win.open() is False
        assert win.show_frame(Image.new("RGB", (100, 100))) == []
        assert win.poll_events() == []
        assert win.toggle_fullscreen() is False
        win.close()
